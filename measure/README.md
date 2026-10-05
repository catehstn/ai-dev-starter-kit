# measure/

Scripts for measuring what an AI-assisted engineering team is actually shipping, from the team's own GitHub repo. They answer five questions:

1. **What kind of work merged?** Merged PRs per month by kind: features, fixes, tests, infra, other.
2. **How much CI effort did it take?** Commits to green, checks per push, rerun rounds, and the share of PRs that touched tests.
3. **How did the guardrails grow?** Month-end snapshots of CLAUDE.md lines, guard scripts, agent hooks, CI workflows and test files, next to checks per push.
4. **How much of the work is safety work?** PRs that are dedicated tests/infra work or carry their own tests, and feature PRs that ship with tests.
5. **Are fixes catching code before release, or fixing prod?** Each fix PR, split into caught before release, fixing code that shipped in the last 7 days, and fixing older code.

Python 3 standard library, the [`gh` CLI](https://cli.github.com/) (logged in) and `git`. Nothing to install.

---

## Why measure this

When most of the code is written by agents, you can't coach by reading every diff, and "how's it going?" gets you a feeling. CI data is a signal that doesn't come from a person: it doesn't have a good or bad week, and it doesn't round up. It tells you where the effort is going (are we only shipping features, or also tests and hardening?), whether the guardrails are keeping up with the throughput, and whether fixes are landing before users see the bug or after.

Use the numbers to ask better questions, not to grade anyone. A month where commits-to-green jumps is a prompt to look at what changed, not a verdict.

---

## Run it

```bash
mkdir -p ~/measure-data && cd ~/measure-data     # outputs land here, not in this repo
M=/path/to/ai-dev-starter-kit/measure

# 1. merged PRs -> prs.csv (one API call)
python3 $M/pull_prs.py --repo owner/name --since 2026-01-01 --base main --skip-bots

# 2. CI columns -> prs.csv (paced, ~1s per API call; resumable)
python3 $M/ci_enrich.py --repo owner/name
#    exit code 1 = some rows have no CI data. It lists them; re-run with --only <numbers>.
python3 $M/ci_enrich.py --repo owner/name --check   # validate without API calls

# 3. the five measures (no API calls)
python3 $M/work_mix.py                                   # 1 and 2 (--by week for weekly)
python3 $M/guardrails.py --clone ~/src/name --since 2026-01-01 --csv prs.csv   # 3
python3 $M/safety_ratio.py                               # 4
python3 $M/fix_timing.py --clone ~/src/name --release-branch origin/release    # 5
#   or, if you release by tagging main:  --release-tags 'v*'
```

Run `git fetch` in the clone before steps 3 and 5. Both are read-only against it.

To keep the data current, re-run steps 1 and 2 with a recent `--since`. `pull_prs.py` merges into the existing `prs.csv`: rows you already enriched keep their CI data, and category edits you made by hand are kept.

Every script takes `--help`.

### Pacing

The scripts wait about 1 second between GitHub API calls (`--pace` to change it). The REST limit is 5,000 calls an hour per token, and if your agents run on the same token they share that budget. A full pull costs one call per PR plus one per commit, so a few months of an active repo is thousands of calls. Pacing keeps the pull from starving everything else. It's slow on purpose: run step 2 in the background and come back.

---

## prs.csv

One CSV holds everything. Steps 1 and 2 write it; everything else reads it. Edit it by hand if you want (fix a category, delete rows), then re-run the reports.

| Column | Written by | Meaning |
|---|---|---|
| `number` | pull | PR number |
| `title` | pull | PR title (quoted when it has commas; always read with a CSV parser, never `cut -d,`) |
| `author` | pull | login; GitHub Apps show as `app/<name>` |
| `category` | pull | `features`, `fixes`, `tests`, `infra` or `other`, from the title |
| `created`, `merged` | pull | dates, `YYYY-MM-DD` (UTC) |
| `month`, `iso_week` | pull | of the merge, `YYYY-MM` and `YYYY-Www` |
| `open_hours` | pull | created to merged |
| `additions`, `deletions` | pull | lines |
| `base` | pull | branch it merged into |
| `head_sha` | pull | the PR's last commit |
| `merge_commit` | pull | the commit it became on the base branch (used by fix timing) |
| `commits` | enrich | commits on the PR: pushes until it was mergeable ("commits to green") |
| `final_checks` | enrich | check runs on the last commit ("checks per push") |
| `total_checks` | enrich | check runs across all the PR's commits |
| `rerun_churn` | enrich | `total_checks - final_checks`: checks spent on earlier commits |
| `rerun_rounds` | enrich | `rerun_churn / final_checks`: roughly, how many earlier full CI rounds |
| `contains_tests` | enrich | `1` if any changed file looks like a test, else `0` |
| `test_files_touched` | enrich | how many |
| `ci_status` | enrich | `ok`, or `error: ...` if a call failed. Blank = not enriched yet |

Reports only use rows with `ci_status=ok`, and say how many they left out.

---

## Reading the numbers

- **Category is a title heuristic.** It reads conventional-commit-style prefixes (`feat:`, `fix(api):`, `chore(deps):`). If your team doesn't title PRs that way, most PRs land in `other`. Edit `CATEGORY_PREFIXES` in `prdata.py`, or fix rows in the CSV. Pure title categories understate safety work, because hardening often gets titled as a feature or a chore.
- **% PRs with tests is the better test number.** It counts PRs that changed a test file, whatever the title. The `tests` category only counts PRs whose title says so.
- **Checks per push measures the guardrail surface.** It grows as you add CI jobs. Commits to green and rerun rounds tell you whether the guardrails cost more effort per PR. Don't quote raw `rerun_churn` over time: it multiplies the growth in checks per push and reads as a regression that isn't there.
- **Check counts drift upward.** Re-running a job adds check runs to that commit, so re-measuring an old month later gives slightly higher numbers. Expected, not a bug.
- **0 check runs is a warning, not an error.** Fine if that path has no CI. If you use commit statuses instead of check runs (older CI integrations), every row will warn and the CI columns won't mean much.
- **Fix timing assumes "in prod" means reachable from your release branch (or release tags) with the same SHAs as main.** That holds if you promote by merging or fast-forwarding main, or by tagging main. It does not hold if you cherry-pick onto the release branch: new SHAs, so everything reads as caught before release. It judges each fix by the most recent change to the lines it touched. Fix PRs scoped `ci`, `build`, `test` and the like, or that only touch test/CI files, count as `tooling`. Change the list with `--tooling-scopes`, and the 7-day line with `--young-days`.
- **Guard scripts need your pattern.** The default `--guards` regex counts files under a `scripts/` directory with `guard`, `lint-` or `check-` in the name. Set it to match where your guards live.
- **GitHub search returns at most 1,000 PRs.** `pull_prs.py` stops if it hits that; pull one month at a time.
- **These are signals, not scores.** They're useful as trends inside one team. Comparing teams or people with them tells you more about how they title PRs than how they work.

---

## Tests

```bash
python3 -m unittest discover measure    # from the repo root
```
