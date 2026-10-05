#!/usr/bin/env python3
"""Step 1: pull merged PRs into prs.csv and categorise them by title.

    python3 pull_prs.py --repo owner/name --since 2026-01-01 [--until 2026-03-31] [--base main] [--out prs.csv]

If --out already exists, new PRs are added and existing rows (including CI columns you
already paid for) are kept. A re-pulled PR keeps its CI data; its title-derived columns
are refreshed unless you hand-edited `category` (that edit is kept). After changing the
categoriser, pass --recategorise to re-derive every category. Use --replace to start over.
"""
import argparse
import datetime as dt
import os
import sys

import prdata

FIELDS = 'number,title,author,createdAt,mergedAt,additions,deletions,baseRefName,headRefOid,mergeCommit'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', required=True, help='owner/name')
    ap.add_argument('--since', required=True, type=dt.date.fromisoformat, help='YYYY-MM-DD, merged on or after')
    ap.add_argument('--until', type=dt.date.fromisoformat, help='YYYY-MM-DD, merged on or before (default: today)')
    ap.add_argument('--base', help='only PRs into this base branch (e.g. main; leaves out release promotions)')
    ap.add_argument('--out', default='prs.csv')
    ap.add_argument('--limit', type=int, default=1000, help='GitHub search returns at most 1000 results')
    ap.add_argument('--replace', action='store_true', help='overwrite --out instead of merging into it')
    ap.add_argument('--skip-bots', action='store_true',
                    help='leave out PRs opened by GitHub Apps (dependabot, renovate, ...)')
    ap.add_argument('--recategorise', action='store_true',
                    help='re-derive category for every row from its title (drops hand edits)')
    a = ap.parse_args()

    until = a.until or dt.date.today()
    query = f'merged:{a.since.isoformat()}..{until.isoformat()}'
    args = ['pr', 'list', '--repo', a.repo, '--state', 'merged', '--limit', str(a.limit),
            '--search', query, '--json', FIELDS]
    if a.base:
        args += ['--base', a.base]
    prs = prdata.Paced().gh_json(*args)
    if len(prs) >= a.limit:
        sys.exit(f'Got {len(prs)} PRs, which is the --limit. Results are truncated; '
                 'split the window (e.g. one month per run) and run again. Nothing written.')

    if a.skip_bots:
        prs = [p for p in prs if not prdata.is_bot((p.get('author') or {}).get('login', ''))]
    fresh = {str(p['number']): prdata.pr_row(p) for p in prs if p.get('mergedAt')}
    existing = {}
    if os.path.exists(a.out) and not a.replace:
        existing = {r['number']: r for r in prdata.read_prs(a.out)}

    merged = dict(existing)
    for n, row in fresh.items():
        old = existing.get(n)
        if old:
            keep_cat = old['category'] != prdata.categorise(old['title'])  # hand-edited
            for c in prdata.PR_COLUMNS:
                if not (c == 'category' and keep_cat):
                    old[c] = row[c]
        else:
            merged[n] = {**row, **{c: '' for c in prdata.CI_COLUMNS}}

    if a.recategorise:
        for r in merged.values():
            r['category'] = prdata.categorise(r['title'])
    if existing and len(merged) < len(existing):
        sys.exit('Row count went down; refusing to write.')  # belt and braces
    prdata.write_prs(a.out, list(merged.values()))
    added = len(merged) - len(existing)
    print(f'{a.out}: {len(fresh)} PRs merged {a.since}..{until} in {a.repo}; '
          f'{added} new, {len(merged)} rows total.')
    print('Spot-check the category column; edit misfiles by hand (edits survive re-pulls).')


if __name__ == '__main__':
    main()
