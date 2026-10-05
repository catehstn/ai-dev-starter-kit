#!/usr/bin/env python3
"""Measures 1 and 2: what kind of work merged, and how much CI effort it took.

    python3 work_mix.py [--csv prs.csv] [--by month|week]

Table 1: merged PRs per period by category (title heuristic).
Table 2: CI effort per period, from rows with complete CI data only:
  commits_to_green  mean commits per PR (pushes until it was mergeable)
  checks_per_push   median check runs on the final commit (size of the guardrail surface)
  rerun_rounds      mean (checks on earlier commits / checks on the final one)
  with_tests        share of PRs that changed at least one test file
"""
import argparse
import collections
import statistics

import prdata


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--csv', default='prs.csv')
    ap.add_argument('--by', choices=('month', 'week'), default='month')
    a = ap.parse_args()
    key = 'month' if a.by == 'month' else 'iso_week'

    rows = prdata.read_prs(a.csv)
    by = collections.defaultdict(list)
    for r in rows:
        by[r[key]].append(r)

    cats = prdata.CATEGORIES + sorted({r['category'] for r in rows} - set(prdata.CATEGORIES))
    print(f'Merged PRs by kind of work (title heuristic), per {a.by}')
    print(f"{a.by:9} {'PRs':>5}  " + '  '.join(f'{c:>9}' for c in cats))
    for k in sorted(by):
        c = collections.Counter(r['category'] for r in by[k])
        n = len(by[k])
        print(f'{k:9} {n:5}  ' + '  '.join(f'{c[x]:4} {prdata.pct(c[x], n):>4}' for x in cats))

    good = prdata.complete(rows)
    skipped = len(rows) - len(good)
    print(f'\nCI effort per {a.by} ({len(good)} PRs with complete CI data'
          + (f'; {skipped} left out, run ci_enrich.py --check' if skipped else '') + ')')
    print(f"{a.by:9} {'PRs':>5}  {'commits_to_green':>16}  {'checks_per_push':>15}  {'rerun_rounds':>12}  {'with_tests':>10}")
    gby = collections.defaultdict(list)
    for r in good:
        gby[r[key]].append(r)
    for k in sorted(gby):
        rs = gby[k]
        commits = statistics.mean(int(r['commits']) for r in rs)
        cpp = statistics.median(int(r['final_checks']) for r in rs)
        rr = [float(r['rerun_rounds']) for r in rs if r['rerun_rounds']]
        tests = sum(r['contains_tests'] == '1' for r in rs)
        print(f'{k:9} {len(rs):5}  {commits:16.1f}  {cpp:15g}  '
              f"{(f'{statistics.mean(rr):.1f}' if rr else '-'):>12}  {prdata.pct(tests, len(rs)):>10}")
    if good:
        t = sum(r['contains_tests'] == '1' for r in good)
        print(f'\nOverall: {prdata.pct(t, len(good))} of {len(good)} PRs touched tests.')


if __name__ == '__main__':
    main()
