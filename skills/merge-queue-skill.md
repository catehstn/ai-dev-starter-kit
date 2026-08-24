---
name: merge-queue
description: Serially drain a PR merge queue from a single operator terminal. Use when asked to "drain the merge queue", "run the merge queue", "merge the queue", "process queued PRs", or when acting as the designated merge orchestrator. Solves the strict-up-to-date collision where multiple agent sessions racing to update-branch + merge step on each other. Use this as a substitute when your host's native merge queue is unavailable (e.g. not offered on your plan tier).
---

# Merge Queue (orchestrator drainer)

## Why this exists

Consider a `main` branch with branch protection set to **strict / up-to-date required** — a PR can only merge when its branch is up to date with `main`. Every merge therefore bumps the *other* ready PRs `BEHIND`, forcing an update-branch + CI re-run. When several agent sessions each try to update + merge independently, they race: double update-branch, merges landing out from under each other, wasted CI.

A native merge queue would fix this, but it isn't always available (some hosting plan tiers don't offer it). The substitute below is a documented-discipline queue you run yourself.

The substitute: **one operator, one terminal, serial draining.** Other sessions hand off by labelling a PR; the single drainer merges them one at a time.

## The model

- **Handoff label:** a `merge-queue` label on the repo. Adding it means: *"reviewed, ready, orchestrator please merge."*
- **Who adds it:** any session, once a PR is reviewed and the author/owner wants it merged. Adding the label is the explicit human/owner authorization to merge — so it also satisfies the "only a deliberate act merges a PR" norm (incl. not merging someone's PR out from under them).
- **Who drains it:** exactly ONE operator at a time (you, in a dedicated terminal — or a teammate running this same skill). Never run two drainers concurrently.
- **Order:** FIFO by PR number (lowest first). Urgent jumps: just merge that PR out of band, then resume.
- **Strict mode stays ON.** `main` is always green in its exact merged state. The cost — needing a drainer running — is the deliberate trade.

## Board status (optional)

If your team tracks issues on a project board through a **Status** field (`Backlog → Ready → In progress → In review → Done`), keep it in sync as you drain: while a PR sits in the merge queue, its linked issue should show **In review**; once merged, **Done**. The drainer is the single sync point for these transitions.

Helper — set the Status of every issue a PR closes (no-op if the PR closes nothing or the issue isn't on the board). Fill in your board's project id, Status field id, and option ids:
```bash
mq_set_status() {  # $1 = PR number, $2 = status-option id
  for iss in $(gh pr view "$1" --repo <your-org>/<your-repo> \
                 --json closingIssuesReferences --jq '.closingIssuesReferences[].number'); do
    item=$(gh project item-list <project-number> --owner <your-org> --limit 500 --format json \
      | jq -r --argjson n "$iss" '.items[] | select(.content.number==$n) | .id')
    [ -n "$item" ] && gh project item-edit --id "$item" --project-id <PROJECT_ID> \
      --field-id <STATUS_FIELD_ID> --single-select-option-id "$2"
  done
}
```

Called from the drain loop below: **In review** when a PR is in the queue, **Done** after it merges.

## Before you start (single-operator lock)

Only one drainer may run at a time, or you reintroduce the collision you're solving.

1. Check wherever your team records an active-operator claim (a shared coordination file, a pinned issue, etc.) for an active "draining merge queue" claim by someone else. If present and fresh (< 30 min), stop — coordinate first.
2. Claim it: record a line — `YYYY-MM-DD HH:MM — <you> draining merge queue` — where teammates will see it.
3. Release it (remove the line) when the queue is empty or you stop.

## Drain algorithm

Repeat until no open PR carries the `merge-queue` label:

1. **List the queue (FIFO):**
   ```
   gh pr list --repo <your-org>/<your-repo> --state open --label merge-queue \
     --json number,title,isDraft,mergeable,mergeStateStatus,baseRefName --jq 'sort_by(.number)'
   ```
   Then, if you track a board, reflect the queue on it — mark each queued PR's linked issue **In review**:
   ```
   for n in <queued PR numbers>; do mq_set_status "$n" <in-review-option-id>; done
   ```
2. **Pick the lowest-numbered PR.** If none, the queue is empty — release the lock and report.
3. **Validate it — skip + flag (remove label, comment why) if any of:**
   - `isDraft: true`
   - `baseRefName != "main"` (this drainer only lands `main`-targeted PRs)
   - `mergeable: "CONFLICTING"` → also add `blocked:dependency`, comment that it needs a manual rebase/conflict-fix, move on.
4. **If `mergeStateStatus == "BEHIND"`**, bring it up to date (this triggers a fresh CI run):
   ```
   gh pr update-branch <n> --repo <your-org>/<your-repo>
   ```
   Updating merges `main` in, which can introduce *semantic* conflicts that types + tests pass over — the review in step 6 is the gate for those. **Don't dispatch the review yet** — gate it on green CI first (step 5).
5. **Wait for the authoritative required checks to complete.** Read the required check names live from the branch-protection config — don't hardcode them:
   ```
   gh pr checks <n> --repo <your-org>/<your-repo> --watch --interval 20
   ```
   Confirm the *terminal* state before acting — don't trust a watcher's exit code. `gh run watch --exit-status` has returned 0 mid-run; re-read the live state (`gh pr checks <n> --required`, or `gh run view <id> --json status,conclusion` and require `status == "completed"`) before you treat a PR as green or merge it.
   - **Checks failed** → remove the `merge-queue` label, comment with the failing check + link, leave the PR for its owner, move to the next. Do not retry a failing PR in the same drain pass. A failing test is often itself the signal the diff is incomplete — e.g. the change removed behaviour an existing test still asserts — so it goes back to the owner; don't spend a review on a red PR.
6. **Once the required checks are green, dispatch the review agent** on the post-update diff (`git diff origin/main...HEAD` for the PR head). Run it read-only in a throwaway worktree (`git worktree add --detach … origin/<head>`; remove it after). It is the gate for the *semantic* conflicts CI can't see, and returns a verdict: ship / ship-with-nits / needs-changes. Tell it to **also flag any existing test the diff makes stale or broken** (e.g. an assertion on text/behaviour the change removed), not just whether new tests were added. Reviewing only after green means no review effort is wasted on a PR that can't merge, and the green suite is itself evidence the diff is internally consistent.

   The review is the *drain gate*, and its ordering matters: **CI green → scan the diff for leaked secrets / PII → lint clean → flag any behaviour change the tests don't cover → then merge-or-hold.** A behaviour change with no anchoring test is a hold, not a merge.
7. **Merge** once **both** gates pass — `mergeStateStatus == "CLEAN"` AND the review verdict is ship / ship-with-nits (not needs-changes):
   ```
   gh pr merge <n> --repo <your-org>/<your-repo> --squash --auto --delete-branch
   ```
   `--auto` is belt-and-suspenders (lands the instant it's green); with a CLEAN state it merges immediately. Use whatever merge method + branch-cleanup your repo conventions call for.
8. **Confirm merged** (`gh pr view <n> --json state,mergedAt`), then, if you track a board, move its closed issue(s) to **Done**: `mq_set_status <n> <done-option-id>`. The next queued PR is now `BEHIND` — it gets handled in its own turn at step 4. **Loop.**

## Safety rules

- **Never** merge a PR that lacks the `merge-queue` label, even if it's green and you can see it.
- **Never** merge a draft, a non-`main`-targeted PR, or a `CONFLICTING` PR.
- The label is the authorization. If you're an agent session and unsure whether a PR is *meant* to be merged, do not add the label — ask the human first.
- Second identical CI failure on the same PR → diagnose, don't keep re-running. Pull it from the queue and flag.
- Respect repo norms for whose PRs get merged: this skill *executes* an already-authorized merge (the label); it does not decide that a PR should merge. The drainer is an **impartial gate, enforced consistently** — same checks, same order, every PR — not a place to make case-by-case exceptions.

## Suspect signals — false failures & split-brain PR heads

The mechanics here run over `gh`/CI/network, all of which throw *transient* false signals. Treat these as suspect, not ground truth — a wrong read costs a wasted drain cycle or a stuck PR.

- **Transient vs real failure.** A required check that fails on a network blip, runner timeout, or infra flake is not the same as a red test. Before pulling a PR from the queue for a "failure," glance at *why* it's red: an assertion diff is real (owner's problem — remove label, comment, move on); an infrastructure / `Cannot connect` / cancelled-runner failure is transient. **Retry a transient once** (`gh run rerun <id> --failed`) before escalating. Don't retry a genuine test failure — and never a *second identical* failure (that's the diagnose-don't-retry rule, above).
- **Split-brain / stale PR head.** Symptom: `gh pr view` shows a `headRefOid` that doesn't match the actual tip of the branch (`gh api repos/…/branches/<head>`), so `mergeStateStatus` is stuck `BEHIND`/`UNKNOWN` and `update-branch` no-ops or loops. The host's PR-head ref has lagged the branch. **Resync by close→reopen:** `gh pr close <n>` then `gh pr reopen <n>` — this forces a re-read of the branch tip and recomputes mergeability. Re-check state before proceeding. (Preserves the branch, the diff, and the `merge-queue` label; it's a ref-refresh, not a rebuild.)
- **Don't trust a single green/red read on a flaky call.** If a state looks wrong given what you just did (e.g. `CLEAN` right after pushing, or `BEHIND` right after a successful update-branch), re-read once before acting — the API is eventually-consistent under load.

## Restart recovery (operator process died, or you stepped away)

Background review agents are tied to the operator process — if it exits mid-drain (crash, restart, or you step away and the session ends), in-flight reviews are lost. The **queue is not**: membership is the `merge-queue` label, the lock lives wherever you recorded your claim, and PR/CI state is on the host. Recovery just re-establishes the in-flight work.

On starting or resuming a drain:

1. **Reclaim a stale lock.** If the active-operator claim is your own from a dead session, or is older than ~30 min, treat it as stale and overwrite it with a fresh claim. Don't block on a dead claim.
2. **Sweep orphaned review worktrees.** `git worktree list | grep <review-worktree-prefix>` → `git worktree remove <path> --force` for any left behind; each is a review that didn't finish.
3. **Re-dispatch mid-flight reviews.** For every PR still carrying the `merge-queue` label that isn't merged and has no completed verdict in hand, re-run its review (read-only, cheap, idempotent), then resume the normal drain.

When the harness sends an agent-failure notification mid-drain ("was running when the process exited"), do steps 2–3 for that PR immediately — don't wait for a restart.

## Notes

- Required checks and `strict` are read live from the branch-protection config (`gh api repos/<your-org>/<your-repo>/branches/main/protection`). If they change, this skill needs no edit — it reads them live.
- If collisions persist even with a single drainer, the next hardening step is a real mutex (e.g. a pinned "Merge queue control" issue self-assigned by the active drainer). Documented discipline first.
- Worktree hygiene: the drain itself runs via `gh` API/CLI calls and needs no local checkout. The only exception is the post-green review agent (step 6), which uses a throwaway `--detach` worktree it must remove when done — never the main checkout (another session may be on the PR's branch).

## Living document

Update this skill when:
- Your CI / final-validation gates change
- You move to (or from) a native merge queue — e.g. GitHub Enterprise
- A new failure mode in landing PRs emerges and needs handling
