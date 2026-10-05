#!/usr/bin/env python3
"""Measure 4: how much of the work is safety work.

    python3 safety_ratio.py [--csv prs.csv]

Per month, from rows with complete CI data:
  dedicated_safety  PRs whose category is tests or infra
  carry_tests       PRs that changed at least one test file, whatever their category
  either            dedicated safety work or carries its own tests
  feature_w_tests   feature PRs that changed at least one test file

Categories come from the title heuristic, which files a lot of real work under "other".
If you hand-correct the category column in prs.csv, this picks it up.
"""
import argparse
import collections

import prdata

SAFETY = {'tests', 'infra'}


def tally(rows):
    by = collections.defaultdict(collections.Counter)
    for r in rows:
        safety = r['category'] in SAFETY
        tests = r['contains_tests'] == '1'
        b = by[r['month']]
        b['n'] += 1
        b['safety'] += safety
        b['tests'] += tests
        b['either'] += safety or tests
        b['feat'] += r['category'] == 'features'
        b['feat_tests'] += r['category'] == 'features' and tests
    return by


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--csv', default='prs.csv')
    a = ap.parse_args()
    rows = prdata.read_prs(a.csv)
    good = prdata.complete(rows)
    if len(good) < len(rows):
        print(f'({len(rows) - len(good)} PRs left out: no CI data. Run ci_enrich.py --check.)')
    p = prdata.pct
    print(f"{'month':8} {'PRs':>5}  {'dedicated_safety':>16}  {'carry_tests':>11}  {'either':>6}  {'feature_w_tests':>15}")
    for m, b in sorted(tally(good).items()):
        print(f"{m:8} {b['n']:5}  {p(b['safety'], b['n']):>16}  {p(b['tests'], b['n']):>11}  "
              f"{p(b['either'], b['n']):>6}  {p(b['feat_tests'], b['feat']):>15}")


if __name__ == '__main__':
    main()
