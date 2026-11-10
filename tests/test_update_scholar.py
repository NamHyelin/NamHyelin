import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

script = Path(__file__).resolve().parents[1] / 'scripts/update_scholar.py'
spec = importlib.util.spec_from_file_location('updater', script)
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
ID = 'KTjNYtAAAAAJ'


def row(title='Paper', count='9', year='2025', key='one', author=ID):
    return f'''<tr class="gsc_a_tr"><td class="gsc_a_t"><a class="gsc_a_at"
    href="/citations?view_op=view_citation&amp;citation_for_view={author}:{key}">{title}</a>
    <div class="gs_gray">H Nam, A Author</div><div class="gs_gray">Journal</div></td>
    <td class="gsc_a_c"><a class="gsc_a_ac gs_ibl">{count}</a><span>*</span></td>
    <td class="gsc_a_y"><span>{year}</span></td></tr>'''


class Tests(unittest.TestCase):
    def test_sort_counts_and_nested_title(self):
        page = '<table>' + row('Low', '9') + row('High <b>&amp; detail</b>', '1,234', key='two') + '</table>'
        papers = u.normalize(page, ID)
        self.assertEqual([p['citations'] for p in papers], [1234, 9])
        self.assertEqual(papers[0]['title'], 'High & detail')
        self.assertEqual(papers[0]['authors'], 'H Nam, A Author')

    def test_missing_count_and_year(self):
        p = u.normalize(row(count='', year=''), ID)[0]
        self.assertEqual(p['citations'], 0)
        self.assertEqual(p['year'], '')

    def test_wrong_profile_rejected(self):
        with self.assertRaises(ValueError):
            u.normalize(row(author='someoneelse'), ID)

    def test_challenge_rejected(self):
        with self.assertRaises(ValueError):
            u.normalize('<html>Please verify you are human</html>', ID)

    def test_changed_markup_rejected(self):
        with self.assertRaises(ValueError):
            u.normalize(row().replace('gsc_a_ac', 'new_class'), ID)

    def test_readme_and_escape(self):
        original = 'My intro\n' + u.START + '\nold\n' + u.END + '\nMy projects\n'
        result = u.update_block(original, 'new')
        self.assertEqual(result, original.replace('\nold\n', '\nnew\n'))
        self.assertIn('&#124;', u.escape('a|b'))
        self.assertIn('&lt;', u.escape('<img>'))

    def test_duplicate_markers_fail(self):
        with self.assertRaises(ValueError):
            u.update_block(u.START + u.START + u.END, 'test')

    def test_failed_fetch_preserves_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'scholar-config.json').write_text(json.dumps({'scholar_id': ID, 'top_n': 4}))
            (root / 'README.md').write_text('Existing README')
            (root / 'data').mkdir()
            (root / 'data/scholar.json').write_text('Existing snapshot')
            with patch.object(sys, 'argv', ['update', '--root', folder]), patch.object(u, 'fetch', side_effect=ValueError('HTTP 429')):
                with self.assertRaises(ValueError):
                    u.main()
            self.assertEqual((root / 'README.md').read_text(), 'Existing README')
            self.assertEqual((root / 'data/scholar.json').read_text(), 'Existing snapshot')

    def test_saved_html_end_to_end_and_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'scholar-config.json').write_text(json.dumps({'scholar_id': ID, 'top_n': 1}))
            (root / 'README.md').write_text('Keep this intro\n')
            (root / 'page.html').write_text('<table>' + row() + row('Top paper', '22', key='two') + '</table>')
            with patch.object(sys, 'argv', ['update', '--root', folder, '--html', str(root / 'page.html')]), patch.object(u, 'fetch') as fetch:
                u.main()
                fetch.assert_not_called()
            snapshot = json.loads((root / 'data/scholar.json').read_text())
            self.assertEqual(snapshot['acquisition'], 'saved_html')
            self.assertEqual(len(snapshot['papers']), 2)
            text = (root / 'README.md').read_text()
            self.assertTrue(text.startswith('Keep this intro'))
            self.assertIn('Top paper', text)
            self.assertNotIn('[Paper]', text)
            with patch.object(sys, 'argv', ['update', '--root', folder, '--from-cache']), patch.object(u, 'fetch') as fetch:
                u.main()
                fetch.assert_not_called()
            self.assertEqual(text, (root / 'README.md').read_text())

if __name__ == '__main__':
    unittest.main()
