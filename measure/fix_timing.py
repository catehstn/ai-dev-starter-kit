#!/usr/bin/env python3
"""Measure 5: were fixes catching code before it shipped, or fixing code already in prod?

    python3 fix_timing.py --clone ~/src/myrepo --release-branch origin/release [--csv prs.csv]
    python3 fix_timing.py --clone ~/src/myrepo --release-tags 'v*'           [--csv prs.csv]

ASSUMPTION: "in prod" means reachable from your release ref, with the same commit SHAs as
main. That holds if you ship by merging or fast-forwarding main into a release branch, or
by tagging commits on main. It does not hold if you cherry-pick onto the release branch
(new SHAs): then everything reads as pre_release. Check this before trusting the output.

For each PR in the `fixes` category:
  1. take its merge commit (merge_commit column) in the local clone
  2. `git blame` the non-test lines it changed or deleted, at the parent commit
     (a pure insertion blames the line just above it, as the nearest context)
  3. take the YOUNGEST blamed commit, i.e. the most recent change to the code being fixed
  4. classify:
       pre_release  that commit had not reached the release ref when the fix merged
       prod_recent  it had, and was at most --young-days old when the fix merged
       prod_older   it had, and was older than that
       tooling      title scope is a tooling scope, or only test/CI files changed
       unknown      merge commit not in the clone, or nothing to blame (new files only)

Read-only against the clone. Run `git fetch` in it first. Writes per-PR detail to --out.
"""
import argparse
import collections
import csv
import datetime as dt
import os
import re
import sys

import prdata

TOOLING_PATH_RE = re.compile(r'(^\.github/|(^|/)\.claude/|\.stories\.|(^|/)testdata/|(^|/)fixtures?/)', re.I)


def first_shipped(clone, since, branch=None, tags=None):
    """{commit sha: datetime it first became reachable from the release ref}."""
    if branch:
        log = prdata.git(clone, 'log', branch, '--first-parent', '--reverse', '--format=%H %cI').splitlines()
    else:
        log = prdata.git(clone, 'for-each-ref', '--sort=creatordate',
                         '--format=%(refname) %(creatordate:iso-strict)', f'refs/tags/{tags}').splitlines()
    points = [(ref, dt.datetime.fromisoformat(when)) for ref, when in (l.split(' ', 1) for l in log)]
    if not points:
        sys.exit('No release history found. Check --release-branch / --release-tags and run git fetch.')
    # Everything shipped before the window: one call, dated by the last release point before it.
    # Exact dates don't matter there; it only has to be "before any fix in the window".
    cutoff = dt.datetime.combine(since, dt.time(), tzinfo=dt.timezone.utc) - dt.timedelta(days=1)
    before = [p for p in points if p[1] < cutoff]
    after = [p for p in points if p[1] >= cutoff]
    shipped = {}
    prev = None
    if before:
        prev, when = before[-1]
        for c in prdata.git(clone, 'rev-list', prev).split():
            shipped[c] = when
    for ref, when in after:
        rng = [ref] if prev is None else [ref, '^' + prev]
        for c in prdata.git(clone, 'rev-list', *rng).split():
            shipped.setdefault(c, when)
        prev = ref
    return shipped


def classify(clone, row, shipped, tooling_scopes, young_days):
    rec = {'number': row['number'], 'title': row['title'], 'month': row['month'], 'cls': '', 'why': '',
           'youngest_blamed': '', 'blamed_age_days': ''}
    m = re.match(r'\s*(?:\[[^\]]*\]\s*)?(?:fix|fixes|bugfix|hotfix|bug)\s*\(([^)]*)\)', row['title'], re.I)
    if m and m.group(1).strip().lower() in tooling_scopes:
        return {**rec, 'cls': 'tooling', 'why': f'scope {m.group(1)}'}
    sha = row.get('merge_commit', '')
    if not sha or prdata.git(clone, 'cat-file', '-t', sha).strip() != 'commit':
        return {**rec, 'cls': 'unknown', 'why': 'merge commit not in clone (git fetch?)'}
    merged_at = dt.datetime.fromisoformat(prdata.git(clone, 'show', '-s', '--format=%cI', sha).strip())
    files = [f for f in prdata.git(clone, 'diff', '--name-only', f'{sha}^', sha).splitlines() if f]
    prod_files = [f for f in files if not (prdata.is_test_path(f) or TOOLING_PATH_RE.search(f))]
    if files and not prod_files:
        return {**rec, 'cls': 'tooling', 'why': 'only test/CI files'}
    blamed = set()
    for f in prod_files:
        diff = prdata.git(clone, 'diff', '-U0', f'{sha}^', sha, '--', f)
        for h in re.finditer(r'^@@ -(\d+)(?:,(\d+))? \+', diff, re.M):
            start, count = int(h.group(1)), int(h.group(2) if h.group(2) is not None else 1)
            if count == 0:  # pure insertion: blame the line above as context
                if start == 0:
                    continue
                count = 1
            bl = prdata.git(clone, 'blame', '--porcelain', '-L', f'{start},+{count}', f'{sha}^', '--', f)
            blamed |= set(re.findall(r'^([0-9a-f]{40}) \d+ \d+', bl, re.M))
    dated = []
    for b in blamed:
        when = prdata.git(clone, 'show', '-s', '--format=%cI', b).strip()
        if when:
            dated.append((dt.datetime.fromisoformat(when), b))
    if not dated:
        return {**rec, 'cls': 'unknown', 'why': 'nothing to blame (new files only?)'}
    when, yb = max(dated)
    age = (merged_at - when).total_seconds() / 86400
    rec.update(youngest_blamed=yb[:12], blamed_age_days=f'{age:.1f}')
    if yb in shipped and shipped[yb] < merged_at:
        rec['cls'] = 'prod_recent' if age <= young_days else 'prod_older'
    else:
        rec['cls'] = 'pre_release'
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--clone', required=True, help='path to a local clone of the repo')
    rel = ap.add_mutually_exclusive_group(required=True)
    rel.add_argument('--release-branch', help='ref that is in prod, e.g. origin/release')
    rel.add_argument('--release-tags', help="tag glob that marks releases, e.g. 'v*'")
    ap.add_argument('--csv', default='prs.csv')
    ap.add_argument('--out', default='fix_timing.csv')
    ap.add_argument('--young-days', type=float, default=7)
    ap.add_argument('--tooling-scopes', default='ci,build,test,tests,e2e,release,deps,hooks',
                    help='comma-separated fix(scope) values that count as tooling, not product code')
    a = ap.parse_args()
    clone = os.path.expanduser(a.clone)
    if a.release_branch:
        prdata.git(clone, 'rev-parse', '--verify', a.release_branch, check=True)

    fixes = [r for r in prdata.read_prs(a.csv) if r['category'] == 'fixes']
    if not fixes:
        sys.exit('No PRs with category=fixes in the CSV.')
    since = min(dt.date.fromisoformat(r['merged']) for r in fixes)
    shipped = first_shipped(clone, since, a.release_branch, a.release_tags)
    scopes = {s.strip().lower() for s in a.tooling_scopes.split(',') if s.strip()}
    out = [classify(clone, r, shipped, scopes, a.young_days) for r in fixes]

    with open(a.out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    classes = ['pre_release', 'prod_recent', 'prod_older', 'tooling', 'unknown']
    by = collections.defaultdict(collections.Counter)
    for o in out:
        by[o['month']][o['cls']] += 1
    d = f'{a.young_days:g}'
    heads = ['pre_release', f'prod_<={d}d', f'prod_>{d}d', 'tooling', 'unknown']
    print(f"{'month':8} {'fixes':>5}  " + '  '.join(f'{h:>11}' for h in heads))
    for m in sorted(by):
        c = by[m]
        print(f'{m:8} {sum(c.values()):5}  ' + '  '.join(f'{c[k]:11}' for k in classes))
    unknown = [o for o in out if o['cls'] == 'unknown']
    if unknown:
        print(f'{len(unknown)} unknown, e.g. #{unknown[0]["number"]}: {unknown[0]["why"]}')
    print(f'Per-PR detail: {a.out}')


if __name__ == '__main__':
    main()
