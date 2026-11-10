#!/usr/bin/env python3
"""Fetch Scholar HTML directly; persist a snapshot and update only marked README text."""
import argparse
from datetime import datetime, timezone
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

START = '<!-- SCHOLAR:START -->'
END = '<!-- SCHOLAR:END -->'


def clean(value):
    return ' '.join(str(value or '').split())


def escape(value):
    value = html.escape(clean(value), quote=False)
    for char in ('\\', '*', '_', '[', ']', '`'):
        value = value.replace(char, '\\' + char)
    return value.replace('|', '&#124;')


def number(value):
    if value is None or value == '':
        return 0
    if isinstance(value, bool):
        raise ValueError('Invalid citation count')
    text = str(value).replace(',', '').strip()
    if not re.fullmatch(r'\d+', text):
        raise ValueError('Invalid citation count')
    return int(text)


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []

    def text(self):
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)

    def select(self, class_name):
        result = []
        if class_name in self.attrs.get('class', '').split():
            result.append(self)
        for child in self.children:
            if isinstance(child, Node):
                result.extend(child.select(class_name))
        return result


class Document(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def normalize(page, scholar_id):
    document = Document()
    document.feed(page)
    rows = document.root.select('gsc_a_tr')
    if not rows:
        raise ValueError('No publication rows found: blocked page, empty profile, or changed Scholar HTML')
    papers, seen = [], set()
    for row in rows:
        titles = row.select('gsc_a_at')
        counts = row.select('gsc_a_ac')
        years = row.select('gsc_a_y')
        if len(titles) != 1 or len(counts) != 1 or len(years) != 1:
            raise ValueError('Unrecognized Scholar row format; existing data is preserved')
        title = clean(titles[0].text())
        if not title:
            raise ValueError('Missing publication title')
        href = titles[0].attrs.get('href', '')
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query)
        citation_id = query.get('citation_for_view', [''])[0]
        if not citation_id.startswith(scholar_id + ':'):
            raise ValueError('Publication belongs to another profile or has no citation ID')
        if citation_id in seen:
            continue
        seen.add(citation_id)
        year = clean(years[0].text())
        if year and not re.fullmatch(r'[0-9]{4}', year):
            raise ValueError('Unrecognized publication year')
        details = row.select('gs_gray')
        params = {'user': scholar_id, 'hl': 'en', 'view_op': 'view_citation',
                  'citation_for_view': citation_id}
        papers.append({'title': title,
                       'authors': clean(details[0].text()) if details else '',
                       'publication': clean(details[1].text()) if len(details) > 1 else '',
                       'year': year, 'citations': number(clean(counts[0].text())),
                       'url': 'https://scholar.google.com/citations?' + urllib.parse.urlencode(params)})
    return sorted(papers, key=lambda paper: (-paper['citations'], paper['title'].casefold()))


def fetch(scholar_id):
    params = {'user': scholar_id, 'hl': 'en', 'pagesize': '100', 'cstart': '0'}
    url = 'https://scholar.google.com/citations?' + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            if urllib.parse.urlsplit(response.url).hostname != 'scholar.google.com':
                raise ValueError('Scholar redirected to a login or challenge page')
            body = response.read(4_000_001)
            if len(body) > 4_000_000:
                raise ValueError('Unexpectedly large Scholar response')
            return body.decode('utf-8')
    except urllib.error.HTTPError as error:
        raise ValueError(f'Scholar HTTP {error.code}; automatic access may be blocked. Existing data is preserved.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError('Could not reach Scholar; existing data is preserved') from None


def render(snapshot, top):
    profile = 'https://scholar.google.com/citations?' + urllib.parse.urlencode({'user': snapshot['scholar_id']})
    lines = ['## Selected Publications', '', f'[Google Scholar]({profile})', '',
             '| Publication | Year | Citations |', '| :--- | ---: | ---: |']
    for paper in snapshot['papers'][:top]:
        lines.append(f"| [{escape(paper['title'])}]({paper['url']}) | {escape(paper['year']) or '—'} | {paper['citations']:,} |")
    lines += ['', f"*Sorted by citation count · Last successful update: {snapshot['fetched_at']}*",
              '*Updated periodically from Google Scholar.*']
    return '\n'.join(lines)


def update_block(original, body):
    block = START + '\n' + body + '\n' + END
    if START not in original and END not in original:
        return original.rstrip() + '\n\n' + block + '\n'
    if original.count(START) != 1 or original.count(END) != 1 or original.index(START) > original.index(END):
        raise ValueError('README must contain exactly one correctly ordered pair of SCHOLAR markers')
    before, rest = original.split(START, 1)
    _, after = rest.split(END, 1)
    return before + block + after


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        out.write(text)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--from-cache', action='store_true', help='Render stored data without making an API request')
    parser.add_argument('--html', type=Path, help='Import a locally saved Scholar HTML page without a network request')
    args = parser.parse_args()
    if args.from_cache and args.html:
        parser.error('--html and --from-cache cannot be combined')
    root = args.root
    config = json.loads((root / 'scholar-config.json').read_text(encoding='utf-8'))
    scholar_id, top = config['scholar_id'], config['top_n']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', scholar_id) or type(top) is not int or not 1 <= top <= 100:
        raise ValueError('Invalid configuration: top_n must be 1–100')
    readme = root / 'README.md'
    original = readme.read_text(encoding='utf-8') if readme.exists() else '# Publications\n'
    update_block(original, '')  # Validate markers before spending an API request.
    data_path = root / 'data' / 'scholar.json'
    if args.from_cache:
        snapshot = json.loads(data_path.read_text(encoding='utf-8'))
        if snapshot['scholar_id'] != scholar_id:
            raise ValueError('Cached data belongs to a different Scholar profile')
    else:
        page = args.html.read_text(encoding='utf-8') if args.html else fetch(scholar_id)
        papers = normalize(page, scholar_id)
        snapshot = {'scholar_id': scholar_id, 'source': 'Google Scholar HTML',
                    'acquisition': 'saved_html' if args.html else 'direct_http',
                    'scope': 'Loaded profile rows (direct HTTP: first page, up to 100)',
                    'fetched_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
                    'papers': papers}
    updated = update_block(original, render(snapshot, top))
    serialized = json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n'
    # No writes occur before fetching, validation, and rendering all succeed.
    if not args.from_cache:
        atomic_write(data_path, serialized)
    atomic_write(readme, updated)
    print(f"Updated README with {min(top, len(snapshot['papers']))} papers; snapshot contains {len(snapshot['papers'])}.")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        # Never print a request URL or raw provider response, which may contain credentials.
        print(f'Update failed: {error}', file=sys.stderr)
        sys.exit(1)
