#!/usr/bin/env python3
"""Measure 5: were fixes catching code before it shipped, or fixing code already in prod?

    python3 fix_timing.py --clone ~/src/myrepo --release-branch origin/release [--csv prs.csv]
    python3 fix_timing.py --clone ~/src/myrepo --release-tags 'v*'           [--csv prs.csv]

ASSUMPTION: "in prod" means reachable from your release ref, with the same commit SHAs
as main, and the release ref records WHEN each release happened:
  --release-branch  promotions are merge commits on the release branch (git merge --no-ff,
                    or a GitHub PR merged with a merge commit). Each promotion is dated by
                    that merge commit. A fast-forwarded release branch records no promotion
                    time (git doesn't keep one), so the script warns if it looks like one;
                    use --release-tags for that setup instead.
  --release-tags    annotated tags (git tag -a), dated by the tagger date. Lightweight tags
                    only carry the commit's date, so the script warns about those.
Cherry-picking onto the release branch makes new SHAs: everything then reads as pre_release.

For each PR in the `fixes` category:
  1. find its change in the local clone: the merge commit against its first parent. If
     that diff is smaller than the PR (a rebase merge only covers the last commit) and
     the CSV has the commit count, the range is widened to cover the whole PR.
  2. `git blame` the non-test lines it changed or deleted, at the commit before the change
     (follows renames; a pure insertion blames the line just above it, as context)
  3. take the YOUNGEST blamed commit, i.e. the most recent change to the code being fixed
  4. classify:
       pre_release  that commit had not reached the release ref when the fix merged
       prod_recent  it had, and was at most --young-days old when the fix merged
       prod_older   it had, and was older than that
       tooling      title scope is a tooling scope, or only test/CI files changed
       unknown      merge commit not in the clone, or nothing could be blamed
Anything that went wrong on the way (blame failures, size mismatch) goes in the `why`
column of --out.

Read-only against the clone. Run `git fetch` in it first.
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


def _cutoff(since):
    # everything released before this is "shipped before any fix in the window"
    return dt.datetime.combine(since, dt.time(), tzinfo=dt.timezone.utc) - dt.timedelta(days=1)


def release_points(clone, branch=None, tags=None, main=None, since=None):
    """[(ref, released_at)] oldest first, plus a list of warnings about the dating."""
    warnings = []
    if branch:
        log = prdata.git(clone, 'log', branch, '--first-parent', '--reverse', '--format=%H %cI').splitlines()
        points = [(r, dt.datetime.fromisoformat(w)) for r, w in (l.split(' ', 1) for l in log)]
        if main and since:
            on_main = set(prdata.git(clone, 'rev-list', '--first-parent', main).split())
            recent = [r for r, w in points if w >= _cutoff(since)]
            ff = [r for r in recent if r in on_main]
            if ff:
                warnings.append(
                    f'{len(ff)} of {len(recent)} release-branch commits in the window are also on '
                    f'{main}\'s first-parent history. That looks like a fast-forwarded release branch, '
                    'which records no promotion time: those commits are dated when they merged to main, '
                    'so code reads as shipped earlier than it was. Use --release-tags, or promote with '
                    'merge commits (--no-ff).')
    else:
        refs = prdata.git(clone, 'for-each-ref', '--sort=creatordate',
                          '--format=%(refname) %(objecttype) %(creatordate:iso-strict)',
                          f'refs/tags/{tags}').splitlines()
        points, light = [], 0
        for l in refs:
            ref, kind, when = l.split(' ', 2)
            light += kind != 'tag'
            points.append((ref, dt.datetime.fromisoformat(when)))
        if light:
            warnings.append(
                f'{light} of {len(points)} release tags are lightweight, so they are dated by their '
                'commit, not by when the release happened. Treat prod_* vs pre_release as approximate, '
                'or use annotated tags (git tag -a).')
    return points, warnings


def first_shipped(points, clone, since):
    """{commit sha: when it first became reachable from the release ref}."""
    if not points:
        sys.exit('No release history found. Check --release-branch / --release-tags and run git fetch.')
    cutoff = _cutoff(since)
    before = [p for p in points if p[1] < cutoff]
    after = [p for p in points if p[1] >= cutoff]
    shipped, prev = {}, None
    if before:
        # one call for everything shipped before the window; exact dates don't matter there
        prev, when = before[-1]
        for c in prdata.git(clone, 'rev-list', prev).split():
            shipped[c] = when
    for ref, when in after:
        rng = [ref] if prev is None else [ref, '^' + prev]
        for c in prdata.git(clone, 'rev-list', *rng).split():
            shipped.setdefault(c, when)
        prev = ref
    return shipped


def _size(clone, base, sha):
    adds = dels = 0
    for l in prdata.git(clone, 'diff', '--numstat', '-M', base, sha).splitlines():
        a, d, _ = l.split('\t', 2)
        if a != '-':
            adds, dels = adds + int(a), dels + int(d)
    return adds, dels


def change_base(clone, sha, row):
    """The commit to diff `sha` against so the diff is the whole PR. Returns (base, note)."""
    base = f'{sha}^'
    try:
        want = (int(row['additions']), int(row['deletions']))
    except (KeyError, ValueError):
        return base, ''
    if _size(clone, base, sha) == want:
        return base, ''
    n = int(row['commits']) if str(row.get('commits', '')).isdigit() else 0
    if n > 1 and prdata.git_run(clone, 'rev-parse', '--verify', f'{sha}~{n}').returncode == 0:
        if _size(clone, f'{sha}~{n}', sha) == want:
            return f'{sha}~{n}', f'rebase merge: {n} commits'
    return base, 'diff size != PR size (rebase merge without a commit count?); judged on the merge commit only'


def changed_hunks(clone, base, sha):
    """{(old_path, new_path): [(start, count) in the old file]} for a diff, following renames."""
    out, old, new, header = {}, None, None, False
    for l in prdata.git(clone, 'diff', '-U0', '-M', base, sha).splitlines():
        if l.startswith('diff --git '):
            old = new = None
            header = True  # ---/+++ lines are file names only here, before the first hunk
        elif header and l.startswith('--- '):
            old = None if l == '--- /dev/null' else l[6:]
        elif header and l.startswith('+++ '):
            new = None if l == '+++ /dev/null' else l[6:]
            out.setdefault((old, new), [])
        elif l.startswith('@@ '):
            header = False
            h = re.match(r'@@ -(\d+)(?:,(\d+))? \+', l)
            out.setdefault((old, new), []).append((int(h.group(1)), int(h.group(2) if h.group(2) is not None else 1)))
    return out


def is_tooling_path(p):
    return p is None or prdata.is_test_path(p) or bool(TOOLING_PATH_RE.search(p))


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
    base, note = change_base(clone, sha, row)
    notes = [note] if note else []
    hunks = changed_hunks(clone, base, sha)
    files = list(hunks)
    prod = {k: v for k, v in hunks.items() if not (is_tooling_path(k[0]) and is_tooling_path(k[1]))}
    if files and not prod:
        return {**rec, 'cls': 'tooling', 'why': 'only test/CI files'}
    blamed, failed = set(), []
    for (old, _new), spans in prod.items():
        if old is None:
            continue  # new file: nothing existed to be wrong
        for start, count in spans:
            if count == 0:  # pure insertion: blame the line above as context
                if start == 0:
                    continue
                count = 1
            p = prdata.git_run(clone, 'blame', '--porcelain', '-L', f'{start},+{count}', base, '--', old)
            if p.returncode != 0:
                failed.append(old)
                continue
            blamed |= set(re.findall(r'^([0-9a-f]{40}) \d+ \d+', p.stdout, re.M))
    if failed:
        notes.append(f'blame failed on {len(failed)} hunk(s): {", ".join(sorted(set(failed))[:3])}')
    dated = []
    for b in blamed:
        when = prdata.git(clone, 'show', '-s', '--format=%cI', b).strip()
        if when:
            dated.append((dt.datetime.fromisoformat(when), b))
    if not dated:
        notes.append('nothing to blame (new files only?)')
        return {**rec, 'cls': 'unknown', 'why': '; '.join(notes)}
    when, yb = max(dated)
    age = (merged_at - when).total_seconds() / 86400
    rec.update(youngest_blamed=yb[:12], blamed_age_days=f'{age:.1f}', why='; '.join(notes))
    if yb in shipped and shipped[yb] < merged_at:
        rec['cls'] = 'prod_recent' if age <= young_days else 'prod_older'
    else:
        rec['cls'] = 'pre_release'
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--clone', required=True, help='path to a local clone of the repo')
    rel = ap.add_mutually_exclusive_group(required=True)
    rel.add_argument('--release-branch', help='ref that is in prod, promoted by merge commits, e.g. origin/release')
    rel.add_argument('--release-tags', help="glob for annotated release tags, e.g. 'v*'")
    ap.add_argument('--main-branch', default='origin/HEAD', help='used to spot a fast-forwarded release branch')
    ap.add_argument('--csv', default='prs.csv')
    ap.add_argument('--out', default='fix_timing.csv')
    ap.add_argument('--young-days', type=float, default=7)
    ap.add_argument('--tooling-scopes', default='ci,build,test,tests,e2e,release,deps,hooks',
                    help='comma-separated fix(scope) values that count as tooling, not product code')
    a = ap.parse_args()
    clone = os.path.expanduser(a.clone)
    if a.release_branch:
        prdata.git(clone, 'rev-parse', '--verify', a.release_branch, check=True)
        prdata.git(clone, 'rev-parse', '--verify', a.main_branch, check=True)

    fixes = [r for r in prdata.read_prs(a.csv) if r['category'] == 'fixes']
    if not fixes:
        sys.exit('No PRs with category=fixes in the CSV.')
    since = min(dt.date.fromisoformat(r['merged']) for r in fixes)
    points, warnings = release_points(clone, a.release_branch, a.release_tags, a.main_branch, since)
    for w in warnings:
        print(f'WARNING: {w}\n', file=sys.stderr)
    shipped = first_shipped(points, clone, since)
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
    noted = [o for o in out if o['why'] and o['cls'] != 'tooling']
    if noted:
        print(f'{len(noted)} rows have notes in the why column, e.g. #{noted[0]["number"]}: {noted[0]["why"]}')
    if warnings:
        print(f'{len(warnings)} warning(s) above: read them before quoting these numbers.')
    print(f'Per-PR detail: {a.out}')


if __name__ == '__main__':
    main()
