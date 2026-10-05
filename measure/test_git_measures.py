"""Tests for fix_timing, guardrails and pull_prs against synthetic git repos built in a
temp dir. Run: python3 -m unittest discover measure   (from the repo root)"""
import datetime as dt
import os
import subprocess
import tempfile
import unittest

import fix_timing
import guardrails
import prdata
import pull_prs

_saved_env = {}


def setUpModule():
    # keep the user's git config (signing, hooks, blame settings) out of the tests
    for k, v in {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}.items():
        _saved_env[k] = os.environ.get(k)
        os.environ[k] = v


def tearDownModule():
    for k, v in _saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class Repo:
    def __init__(self, path):
        self.path = path
        self.run('init', '-q', '-b', 'main')

    def run(self, *args, date='2026-01-01T12:00:00+00:00'):
        env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com',
               'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com',
               'GIT_AUTHOR_DATE': date, 'GIT_COMMITTER_DATE': date}
        return subprocess.run(['git', '-C', self.path, *args], env=env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, day, files=None, msg='c', mv=None):
        if mv:
            self.run('mv', *mv)
        for name, body in (files or {}).items():
            full = os.path.join(self.path, name)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(body)
        self.run('add', '-A')
        self.run('commit', '-q', '-m', msg, date=f'{day}T12:00:00+00:00')
        return self.run('rev-parse', 'HEAD')


def fix_row(n, sha, day, **kw):
    return {'number': str(n), 'title': kw.pop('title', 'fix: something'), 'month': day[:7],
            'merge_commit': sha, 'additions': '', 'deletions': '', 'commits': '', **kw}


class FixTiming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        r = cls.r = Repo(cls.tmp.name)
        c0 = r.commit('2026-01-01', {'app.py': 'a1\nb1\nc1\n', 'lib.py': 'x\ny\n', 'q.sql': '-- note\nselect 1;\nx\ny\nselect 2;\n',
                                     'tests/test_app.py': 't1\n'})
        r.run('branch', 'release', c0)
        r.run('branch', 'release-ff', c0)
        r.run('tag', '-a', 'v1', c0, '-m', 'v1', date='2026-01-01T13:00:00+00:00')
        r.run('tag', 'lw1', c0)
        x = r.commit('2026-02-20', {'app.py': 'a1\nb2\nc1\n'})
        # promote main -> release with a merge commit on Feb 21
        r.run('checkout', '-q', 'release')
        r.run('merge', '-q', '--no-ff', 'main', '-m', 'promote', date='2026-02-21T12:00:00+00:00')
        r.run('checkout', '-q', 'main')
        r.run('tag', '-a', 'v2', x, '-m', 'v2', date='2026-02-21T12:00:00+00:00')
        cls.fix_recent = r.commit('2026-02-24', {'app.py': 'a1\nb3\nc1\n'})
        r.commit('2026-02-25', {'app.py': 'a1\nb3\nc2\n'})
        cls.fix_pre = r.commit('2026-02-26', {'app.py': 'a1\nb3\nc3\n'})
        cls.fix_old = r.commit('2026-03-01', {'app.py': 'a3\nb3\nc3\n'})
        # deleting a line that starts with "-- " shows as "--- ..." in the diff: not a file header
        cls.fix_sql = r.commit('2026-03-01', {'q.sql': 'select 1;\nx\ny\nselect 3;\n'})
        cls.fix_tooling = r.commit('2026-03-02', {'tests/test_app.py': 't2\n'})
        cls.fix_rename = r.commit('2026-03-03', {'lib2.py': 'x\ny2\n'}, mv=('lib.py', 'lib2.py'))
        # a rebase-merged 2-commit PR: the merge commit alone only shows the second commit
        r.commit('2026-03-04', {'app.py': 'a4\nb3\nc3\n'})
        cls.fix_rebase = r.commit('2026-03-04', {'new.py': 'n\n'})
        # a later release ships everything; fixes merged before it must still read pre_release
        r.run('checkout', '-q', 'release')
        r.run('merge', '-q', '--no-ff', 'main', '-m', 'promote', date='2026-03-10T12:00:00+00:00')
        r.run('checkout', '-q', 'main')
        r.run('tag', '-a', 'v3', 'main', '-m', 'v3', date='2026-03-10T12:00:00+00:00')
        # fast-forward release-ff onto main after the fixes (the setup that can't be dated)
        r.run('branch', '-f', 'release-ff', cls.fix_recent)
        cls.since = dt.date(2026, 2, 24)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def classify_all(self, **mode):
        points, warnings = fix_timing.release_points(self.r.path, main='main', since=self.since, **mode)
        shipped = fix_timing.first_shipped(points, self.r.path, self.since)
        rows = {
            'recent': fix_row(1, self.fix_recent, '2026-02-24'),
            'pre': fix_row(2, self.fix_pre, '2026-02-26'),
            'old': fix_row(3, self.fix_old, '2026-03-01'),
            'sql': fix_row(8, self.fix_sql, '2026-03-01'),
            'tooling': fix_row(4, self.fix_tooling, '2026-03-02'),
            'scope': fix_row(5, self.fix_old, '2026-03-01', title='fix(ci): flaky job'),
            'rename': fix_row(6, self.fix_rename, '2026-03-03'),
            'rebase': fix_row(7, self.fix_rebase, '2026-03-04', additions='2', deletions='1', commits='2'),
        }
        out = {k: fix_timing.classify(self.r.path, row, shipped, {'ci'}, 7) for k, row in rows.items()}
        return out, warnings

    def check(self, out):
        self.assertEqual(out['recent']['cls'], 'prod_recent')
        self.assertEqual(out['pre']['cls'], 'pre_release')
        self.assertEqual(out['old']['cls'], 'prod_older')
        self.assertEqual((out['sql']['cls'], out['sql']['why']), ('prod_older', ''))
        self.assertEqual(out['tooling']['cls'], 'tooling')
        self.assertEqual(out['scope']['cls'], 'tooling')
        self.assertEqual(out['rename']['cls'], 'prod_older')   # blame followed lib.py -> lib2.py
        self.assertEqual(out['rename']['why'], '')
        # widened to both commits, so it blames the app.py line last changed on Mar 1 (unreleased)
        self.assertEqual(out['rebase']['cls'], 'pre_release')
        self.assertIn('rebase merge', out['rebase']['why'])

    def test_release_branch_with_merge_promotions(self):
        out, warnings = self.classify_all(branch='release')
        self.assertEqual(warnings, [])
        self.check(out)

    def test_annotated_release_tags(self):
        out, warnings = self.classify_all(tags='v*')
        self.assertEqual(warnings, [])
        self.check(out)

    def test_user_diff_noprefix_config(self):
        # diff.noprefix=true drops the a/ b/ prefixes the parser expects unless we pin them
        keys = {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'diff.noprefix', 'GIT_CONFIG_VALUE_0': 'true'}
        saved = {k: os.environ.get(k) for k in keys}
        os.environ.update(keys)
        try:
            out, _ = self.classify_all(branch='release')
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.check(out)

    def test_lightweight_tags_warn(self):
        _, warnings = fix_timing.release_points(self.r.path, tags='lw*')
        self.assertEqual(len(warnings), 1)
        self.assertIn('lightweight', warnings[0])

    def test_fast_forwarded_release_branch_warns(self):
        _, warnings = fix_timing.release_points(self.r.path, branch='release-ff', main='main', since=self.since)
        self.assertEqual(len(warnings), 1)
        self.assertIn('fast-forwarded', warnings[0])

    def test_missing_commit_is_unknown(self):
        out = fix_timing.classify(self.r.path, fix_row(9, '0' * 40, '2026-03-01'), {}, set(), 7)
        self.assertEqual(out['cls'], 'unknown')


class GuardrailSnapshots(unittest.TestCase):
    def test_side_branch_commit_counts_when_merged_not_when_written(self):
        with tempfile.TemporaryDirectory() as d:
            r = Repo(d)
            c0 = r.commit('2026-01-01', {'README': 'x\n', 'CLAUDE.md': 'one\ntwo\n'})
            r.run('checkout', '-q', '-b', 'side', c0)
            r.commit('2026-01-20', {'.github/workflows/ci.yml': 'on: push\n'})
            r.run('checkout', '-q', 'main')
            r.commit('2026-01-15', {'README': 'y\n'})
            r.run('merge', '-q', '--no-ff', 'side', '-m', 'merge side', date='2026-02-10T12:00:00+00:00')
            args = (d, 'main')
            res = (guardrails.re.compile(r'(^|/)CLAUDE\.md$'), guardrails.re.compile('guard'))
            jan = guardrails.snapshot(*args, dt.date(2026, 1, 31), *res)
            feb = guardrails.snapshot(*args, dt.date(2026, 2, 28), *res)
            self.assertEqual(jan['workflows'], 0)
            self.assertEqual(feb['workflows'], 1)
            self.assertEqual(jan['claude_md_lines'], 2)


class PullMerge(unittest.TestCase):
    def row(self, n, title, **kw):
        base = {c: '' for c in prdata.COLUMNS}
        base.update(number=str(n), title=title, category=prdata.categorise(title), **kw)
        return base

    def test_keeps_ci_data_and_hand_edits(self):
        existing = {
            '1': self.row(1, 'feat: a', commits='3', ci_status='ok'),
            '2': self.row(2, 'chore: really a fix', ci_status='ok'),
        }
        existing['2']['category'] = 'fixes'  # edited by hand
        fresh = {
            '1': self.row(1, 'feat: a, renamed'),
            '2': self.row(2, 'chore: really a fix'),
            '3': self.row(3, 'test: new'),
        }
        out = pull_prs.merge_rows(existing, fresh)
        self.assertEqual(sorted(out), ['1', '2', '3'])
        self.assertEqual((out['1']['title'], out['1']['commits'], out['1']['ci_status']),
                         ('feat: a, renamed', '3', 'ok'))
        self.assertEqual(out['2']['category'], 'fixes')
        self.assertEqual(out['3']['ci_status'], '')
        self.assertEqual(existing['1']['title'], 'feat: a')  # input not mutated
        again = pull_prs.merge_rows(existing, fresh, recategorise=True)
        self.assertEqual(again['2']['category'], 'other')


if __name__ == '__main__':
    unittest.main()
