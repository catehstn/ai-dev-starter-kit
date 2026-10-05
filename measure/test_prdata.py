"""Run: python3 -m unittest discover measure   (from the repo root)"""
import datetime as dt
import os
import tempfile
import unittest

import prdata


class Categorise(unittest.TestCase):
    def test_prefixes(self):
        cases = {
            'feat: add export': 'features',
            'feat(api)!: breaking': 'features',
            'fix: null check': 'fixes',
            'Fix the login redirect': 'fixes',
            'hotfix(billing): rounding': 'fixes',
            '[web] fix: typo': 'fixes',
            'test: cover the parser': 'tests',
            'ci: cache deps': 'infra',
            'build(deps): bump x': 'infra',
            'chore(deps): bump x from 1 to 2': 'infra',
            'Bump eslint from 9 to 10': 'infra',
            'fix(deps): pin y': 'fixes',
            'chore: tidy': 'other',
            'docs: readme': 'other',
            'fixture loader rewrite': 'other',   # "fix" must be a whole word
            'Citation support': 'other',         # so must "ci"
            '': 'other',
        }
        for title, want in cases.items():
            self.assertEqual(prdata.categorise(title), want, title)

    def test_test_paths(self):
        for p in ('src/a.test.ts', 'pkg/x_test.go', 'tests/test_a.py', 'web/e2e/login.ts', 'a/__tests__/b.js'):
            self.assertTrue(prdata.is_test_path(p), p)
        for p in ('src/contest.ts', 'src/latest/index.ts', 'README.md'):
            self.assertFalse(prdata.is_test_path(p), p)


class CsvRoundTrip(unittest.TestCase):
    def test_awkward_titles_survive(self):
        pr = {'number': 7, 'title': 'fix: handle "a, b", and\nnewlines', 'author': {'login': 'x'},
              'createdAt': '2026-01-30T22:00:00Z', 'mergedAt': '2026-02-01T10:00:00Z',
              'additions': 3, 'deletions': 1, 'baseRefName': 'main', 'headRefOid': 'abc',
              'mergeCommit': {'oid': 'def'}}
        row = prdata.pr_row(pr)
        self.assertEqual((row['category'], row['month'], row['open_hours']), ('fixes', '2026-02', '36.0'))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'prs.csv')
            prdata.write_prs(path, [row])
            back = prdata.read_prs(path)
        self.assertEqual(back[0]['title'], pr['title'])
        self.assertEqual(back[0]['merge_commit'], 'def')
        self.assertEqual(list(back[0]), prdata.COLUMNS)


class Validation(unittest.TestCase):
    def row(self, n, **kw):
        base = {c: '' for c in prdata.COLUMNS}
        base.update(number=str(n), commits='2', final_checks='5', total_checks='9', ci_status='ok')
        base.update(kw)
        return base

    def test_problems_are_listed_not_zeroed(self):
        rows = [self.row(1), self.row(2, ci_status=''), self.row(3, commits='0'),
                self.row(4, final_checks='NA'), self.row(5, ci_status='error: 502'),
                self.row(6, final_checks='0')]
        errors, warnings = prdata.problems(rows)
        self.assertEqual([n for n, _ in errors], ['2', '3', '4', '5'])
        self.assertEqual([n for n, _ in warnings], ['6'])
        self.assertEqual([r['number'] for r in prdata.complete(rows)], ['1', '6'])


class MonthEnds(unittest.TestCase):
    def test_spans_year_and_clips(self):
        got = prdata.month_ends(dt.date(2025, 11, 15), dt.date(2026, 1, 10))
        self.assertEqual(got, [dt.date(2025, 11, 30), dt.date(2025, 12, 31), dt.date(2026, 1, 10)])


if __name__ == '__main__':
    unittest.main()
