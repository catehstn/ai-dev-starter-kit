"""Shared helpers for the measure/ scripts: the prs.csv schema, the title categoriser,
paced gh calls, git calls, and validation.

Python 3 stdlib only. Needs the `gh` CLI (authenticated) and `git` on PATH.
"""
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

# One CSV, one schema. pull_prs.py writes the first block, ci_enrich.py fills the second.
PR_COLUMNS = [
    'number', 'title', 'author', 'category', 'created', 'merged', 'month', 'iso_week',
    'open_hours', 'additions', 'deletions', 'base', 'head_sha', 'merge_commit',
]
CI_COLUMNS = [
    'commits', 'final_checks', 'total_checks', 'rerun_churn', 'rerun_rounds',
    'contains_tests', 'test_files_touched', 'ci_status',
]
COLUMNS = PR_COLUMNS + CI_COLUMNS

# Title-prefix heuristic. Edit these to match how your team titles PRs.
# Order matters: the first match wins.
CATEGORY_PREFIXES = [
    ('features', ('feat', 'feature')),
    ('fixes', ('fix', 'fixes', 'bugfix', 'hotfix', 'bug')),
    ('tests', ('test',)),
    ('infra', ('ci', 'build', 'release', 'security', 'migration', 'ops', 'deps', 'perf', 'bump')),
]
# A conventional-commit scope that marks infra whatever the type, e.g. "chore(deps): bump x".
INFRA_SCOPES = ('deps', 'deps-dev', 'ci', 'build', 'release')
CATEGORIES = ['features', 'fixes', 'tests', 'infra', 'other']

# A changed path matching this means the PR carries test work, whatever its title says.
TEST_PATH_RE = re.compile(
    r'(\.test\.|\.spec\.|__tests__/|_test\.go$|_test\.py$|(^|/)test_[^/]*\.py$|(^|/)tests?/'
    r'|(^|/)spec/|\.cy\.|(^|/)e2e/|playwright)', re.I)

DEFAULT_PACE = 1.0  # seconds between GitHub API calls; see README "Pacing"


def categorise(title):
    """Map a PR title to one of CATEGORIES by its prefix. A heuristic, not a truth."""
    t = (title or '').strip().lower()
    # strip a leading [tag] so "[api] fix: x" still reads as a fix
    t = re.sub(r'^\[[^\]]*\]\s*', '', t)
    m = re.match(r'\w+\(([^)]*)\)', t)
    if m and m.group(1).strip() in INFRA_SCOPES and not t.startswith(('feat', 'fix')):
        return 'infra'
    for cat, prefixes in CATEGORY_PREFIXES:
        for p in prefixes:
            # whole word only: "fix: x", "fix(api): x", "feat!: x", "Fix the thing" but not "fixture"
            if re.match(re.escape(p) + r'\b', t):
                return cat
    return 'other'


def is_bot(login):
    # gh reports GitHub App authors as "app/<name>"; some bots are plain users named "<x>[bot]"
    return login.startswith('app/') or login.endswith('[bot]')


def is_test_path(path):
    return bool(TEST_PATH_RE.search(path or ''))


def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00'))


def pr_row(pr):
    """Turn one `gh pr list --json` record into a prs.csv row (dict)."""
    created, merged = parse_ts(pr['createdAt']), parse_ts(pr['mergedAt'])
    iso = merged.date().isocalendar()
    return {
        'number': str(pr['number']),
        'title': pr['title'],
        'author': (pr.get('author') or {}).get('login', ''),
        'category': categorise(pr['title']),
        'created': created.date().isoformat(),
        'merged': merged.date().isoformat(),
        'month': merged.strftime('%Y-%m'),
        'iso_week': f'{iso[0]}-W{iso[1]:02d}',
        'open_hours': f'{(merged - created).total_seconds() / 3600:.1f}',
        'additions': str(pr.get('additions', '')),
        'deletions': str(pr.get('deletions', '')),
        'base': pr.get('baseRefName', ''),
        'head_sha': pr.get('headRefOid', '') or '',
        'merge_commit': ((pr.get('mergeCommit') or {}).get('oid') or ''),
    }


# ---- CSV I/O: always a real CSV parser. Titles contain commas and quotes. ----

def read_prs(path):
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for c in COLUMNS:
            r.setdefault(c, '')
            if r[c] is None:
                r[c] = ''
    return rows


def write_prs(path, rows):
    rows = sorted(rows, key=lambda r: int(r['number']))
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in COLUMNS})
    os.replace(tmp, path)  # atomic: a crash mid-write never leaves a half file


# ---- gh / git ----

class Paced:
    """Call `gh` with a fixed gap between calls."""

    def __init__(self, pace=DEFAULT_PACE):
        self.pace = pace
        self._last = 0.0

    def gh(self, *args):
        wait = self._last + self.pace - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            p = subprocess.run(['gh', *args], capture_output=True, text=True)
        finally:
            self._last = time.monotonic()
        if p.returncode != 0:
            raise RuntimeError(f"gh {' '.join(args[:3])}...: {p.stderr.strip()[:200]}")
        return p.stdout

    def gh_json(self, *args):
        return json.loads(self.gh(*args))


def git_run(clone, *args):
    """Run git, return the CompletedProcess (callers that must notice failures use this)."""
    return subprocess.run(['git', '-C', clone, *args], capture_output=True, text=True)


def git(clone, *args, check=False):
    p = git_run(clone, *args)
    if check and p.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed in {clone}: {p.stderr.strip()}")
    return p.stdout


# ---- validation: fail loudly instead of trusting silent zeros ----

def problems(rows):
    """Return (errors, warnings) as lists of (number, reason).

    errors: CI columns missing/NA, the enrich step recorded an error, or 0 commits
            (a real merged PR always has at least one commit).
    warnings: 0 check runs on the final commit. Fine if the repo has no CI on that
              path; suspicious otherwise.
    """
    errors, warnings = [], []
    for r in rows:
        n = r['number']
        if r.get('ci_status', '') not in ('ok',):
            errors.append((n, r.get('ci_status') or 'not enriched yet'))
            continue
        missing = [c for c in ('commits', 'final_checks', 'total_checks') if r.get(c, '') in ('', 'NA')]
        if missing:
            errors.append((n, 'missing ' + ','.join(missing)))
        elif int(r['commits']) == 0:
            errors.append((n, '0 commits'))
        elif int(r['final_checks']) == 0:
            warnings.append((n, '0 check runs on final commit'))
    return errors, warnings


def complete(rows):
    """Rows whose CI data is usable."""
    bad = {n for n, _ in problems(rows)[0]}
    return [r for r in rows if r['number'] not in bad]


def pct(a, b):
    return f'{100 * a / b:.0f}%' if b else '-'


def month_ends(since, until):
    """Last day of each month from `since` to `until`, the final one clipped to `until`."""
    d = dt.date(since.year, since.month, 1)
    out = []
    while d <= until:
        nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        out.append(min(nxt - dt.timedelta(days=1), until))
        d = nxt
    return out
