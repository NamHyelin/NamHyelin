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
            body = response.read(4_000_001)
            if len(body) > 4_000_000:
                raise ValueError('Unexpectedly large Scholar response')
            page = body.decode('utf-8', errors='replace')
            report_response(page, response.status, response.url, response.headers.get('Content-Type', ''))
            if urllib.parse.urlsplit(response.url).hostname != 'scholar.google.com':
                raise ValueError('Scholar redirected to another host; see SCHOLAR_DIAGNOSTICS')
            return page
    except urllib.error.HTTPError as error:
        try:
            page = error.read(4_000_000).decode('utf-8', errors='replace')
        except (OSError, TimeoutError):
            page = ''
        report_response(page, error.code, error.url, error.headers.get('Content-Type', ''))
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
    update_block(original, '')  # Validate markers before requesting Scholar.
    data_path = root / 'data' / 'scholar.json'
    if args.from_cache:
        snapshot = json.loads(data_path.read_text(encoding='utf-8'))
        if snapshot['scholar_id'] != scholar_id:
            raise ValueError('Cached data belongs to a different Scholar profile')
    else:
        page = args.html.read_text(encoding='utf-8') if args.html else fetch(scholar_id)
        if args.html:
            report_response(page)
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
        # Do not print raw response HTML or cookies.
        print(f'Update failed: {error}', file=sys.stderr)
        sys.exit(1)
