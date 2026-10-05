#!/usr/bin/env python3
"""Measure 3: how the guardrails grew, as month-end snapshots of the repo.

    python3 guardrails.py --clone ~/src/myrepo --since 2026-01-01 [--until 2026-06-30]
                          [--branch origin/HEAD] [--csv prs.csv]

For each month end, takes the last commit on --branch before that day and counts:
  claude_md_lines  lines across every file matching --instructions (default: any CLAUDE.md)
  guard_scripts    files matching --guards (purpose-built checks your CI or hooks run)
  agent_hooks      files under .claude/hooks/
  workflows        CI workflow files under .github/workflows/
  test_files       files that look like tests
If --csv is given, adds checks_per_push (median check runs on a PR's final commit that
month) and with_tests (share of that month's PRs that changed a test file).

Read-only against the clone. Run `git fetch` in it first so --branch is current.
"""
import argparse
import collections
import datetime as dt
import os
import re
import statistics

import prdata


def snapshot(clone, branch, day, instr_re, guard_re):
    sha = prdata.git(clone, 'rev-list', '-1', f'--before={day.isoformat()} 23:59:59', branch).strip()
    if not sha:
        return None
    files = prdata.git(clone, 'ls-tree', '-r', '--name-only', sha).splitlines()
    instr = [f for f in files if instr_re.search(f)]
    return {
        'claude_md_lines': sum(prdata.git(clone, 'show', f'{sha}:{f}').count('\n') for f in instr),
        'guard_scripts': sum(1 for f in files if guard_re.search(f)),
        'agent_hooks': sum(1 for f in files if f.startswith('.claude/hooks/')),
        'workflows': sum(1 for f in files if re.match(r'\.github/workflows/[^/]+\.ya?ml$', f)),
        'test_files': sum(1 for f in files if prdata.is_test_path(f)),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--clone', required=True, help='path to a local clone of the repo')
    ap.add_argument('--since', required=True, type=dt.date.fromisoformat)
    ap.add_argument('--until', type=dt.date.fromisoformat, help='default: today')
    ap.add_argument('--branch', default='origin/HEAD', help="default: the remote's default branch")
    ap.add_argument('--csv', help='prs.csv, to add checks_per_push and with_tests per month')
    ap.add_argument('--instructions', default=r'(^|/)CLAUDE\.md$',
                    help=r'regex for agent instruction files, e.g. "(^|/)(CLAUDE|AGENTS)\.md$"')
    ap.add_argument('--guards', default=r'(^|/)scripts/(.*/)?[^/]*(guard|lint-|check-)[^/]*$',
                    help='regex for purpose-built guard scripts; set this to match your repo')
    a = ap.parse_args()
    clone = os.path.expanduser(a.clone)
    prdata.git(clone, 'rev-parse', '--verify', a.branch, check=True)
    instr_re, guard_re = re.compile(a.instructions), re.compile(a.guards)

    by = collections.defaultdict(list)
    if a.csv:
        for r in prdata.complete(prdata.read_prs(a.csv)):
            by[r['month']].append(r)

    print(f"{'month-end':10}  {'claude_md_lines':>15}  {'guard_scripts':>13}  {'agent_hooks':>11}  "
          f"{'workflows':>9}  {'test_files':>10}" + (f"  {'checks_per_push':>15}  {'with_tests':>10}" if a.csv else ''))
    for day in prdata.month_ends(a.since, a.until or dt.date.today()):
        s = snapshot(clone, a.branch, day, instr_re, guard_re)
        if s is None:
            print(f'{day}  (no commits on {a.branch} yet)')
            continue
        line = (f"{day}  {s['claude_md_lines']:15}  {s['guard_scripts']:13}  {s['agent_hooks']:11}  "
                f"{s['workflows']:9}  {s['test_files']:10}")
        if a.csv:
            rs = by.get(day.strftime('%Y-%m'), [])
            cpp = statistics.median(int(r['final_checks']) for r in rs) if rs else '-'
            t = sum(r['contains_tests'] == '1' for r in rs)
            line += f'  {cpp:>15}  {prdata.pct(t, len(rs)):>10}'
        print(line)


if __name__ == '__main__':
    main()
