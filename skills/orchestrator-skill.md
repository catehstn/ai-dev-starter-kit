---
name: pr-orchestrator
description: Orchestrate working through a board of "ready" issues with concurrent background subagents — decompose, dispatch worktree-isolated agents, review, and shepherd PRs to merge-ready, then hand off to the merge-queue skill. Keep at most ~5 in flight at once. Use this whenever asked to "work through the ready issues", "pick up issues", "dispatch agents on the issues", run several PRs concurrently, manage concurrent implementation/review agents, or coordinate a batch of issue-work toward merge — even if "orchestrate" isn't said. This is the dispatch-and-review half; it pairs with the `merge-queue` skill (the serial drainer). Use merge-queue instead when the ask is to drain/merge already-labelled PRs.
---

# PR Orchestrator (dispatch & shepherd)

## Why this exists, and how it pairs with merge-queue

Two complementary roles, deliberately split:

- **pr-orchestrator (this skill)** — decompose a board of `ready` issues, dispatch agents to implement them, review the results, drive each PR to *merge-ready*, then hand off by adding the **`merge-queue`** label. It never merges.
- **merge-queue** — serially drains labelled PRs (update-branch, wait for checks, merge). It never decides *what* should merge; the label is its authorization.

Keep them non-overlapping: the orchestrator's job ends at "reviewed, green, signed-off, labelled." The drainer's job begins there. The label is the seam.

The orchestrator exists because one person can shepherd far more work than they can write by hand — but only if the board stays trustworthy and nothing merges that shouldn't. Most of this skill is about those two things.

## The loop

`triage → scope-check with the human → dispatch (isolated agents) → review (scaled to risk) → verify green → human sign-off → label merge-queue → handle bounces → end-of-session audit`

You run this continuously, many issues in parallel. Stay responsive: dispatch in the background and react to completions as they land.

## How much to run at once — cap it around 5

Keep concurrent in-flight agents/PRs to **roughly 5**. Past that, coordination cost outruns throughput and the failure modes compound: agents stall or finish without notifying you, completions get lost, the serial merge queue can't drain fast enough so rebases pile up, PRs start conflicting with each other on shared files, and you spend effort (and budget) on work that fights itself. This isn't theoretical — pushing well past 5 in a single session produces exactly that: stalled agents, lost completions, rebase churn, and ultimately a hit spend limit.

When you reach the cap, **let work land before dispatching more** — drive the in-flight set to merge-ready and into the queue, then refill from the board. If stalled or silent agents are accumulating, you're already over the line: consolidate and finish what's open rather than adding. Throughput here is gated by the *serial* merge queue, not by how many agents you can spawn — so more than ~5 in flight rarely buys real speed.

## Size each agent's task to fit its context window

A subagent has a finite window, and subagents run *within your session* — so this is about the window, not a separate budget, but a blown window still costs a wasted run and a re-dispatch. A task that's too big — a cross-cutting refactor across a dozen files, an open-ended "find and fix everything" — makes the agent burn its window *exploring* and it can run out before producing anything mergeable (a ~15-file refactor did exactly that: many tool calls, no PR). Two habits prevent it:

- **Hand the agent explicit targets, not a hunt.** List the exact files / call sites / endpoints in the prompt so it spends its window editing, not searching. If you catch yourself writing "find all the places that…", do that grep yourself first and pass the list.
- **Split big cross-cutting work into smaller tasks** — e.g. "create the primitive + its story/tests" as one, "refactor these N call sites" as another (batched if many). Each fits a window and fails small.
- Tell agents to **verify once** (run the gate after the edits are done), not to re-run the whole lint+test+build loop after every tiny change — that's a common window-waster.

## 1. Triage before dispatching

- **Read the work-list from the board's `Ready` column, not a label.** Workflow position lives on your project board's `Status` field. Pull the candidates whose status is `Ready` from your board's API/CLI (e.g. list project items and filter to `status == "Ready"`, emitting `repo#number title`).
- **Open PRs outrank new work.** An open PR is closer to value than an unstarted issue; clear/advance it first.
- **Keep incremental / sliced work moving — don't park it at `In progress`.** Some issues ship as a *series* of small PRs under one issue (an incremental migration, a per-call-site refactor, a multi-page build). For these the **next slice is actionable work even while the issue sits at `In progress`** — when the current slice's PR is queued or merged, dispatch the next slice against the settled tree, and leave the issue at `In progress` until the series is done. Treat them as a standing source of work alongside the `Ready` column, not as "hands off." (Contrast: a *single-deliverable* `In progress` issue is just someone actively on it — leave that one alone.)
- **Pick issues that are agent-able end-to-end** (a fresh agent can finish them from the issue text + repo) **and don't collide** with in-flight branches — especially shared files (test fixtures, route registration, a hot component). Two agents editing the same file means rebase churn through a serial queue.
- **Defer, don't dispatch:** issues blocked on a human/product decision, on external account/key setup (a third-party API token, a monitoring DSN), or owned by someone else. Label those honestly (see §9) rather than starting them.
- **Recommend a batch, don't survey.** Propose 3–5 concrete picks with a one-line why each, flag the conflict/sequencing risks, and get the human's sign-off on scope before you spawn anything.

## 2. Dispatch

- **One worktree per agent**, off the latest `origin/main` (sibling path like `repo-<issue>` or `.worktrees/<branch>` — match the repo's convention). Always `git -C <worktree>`; never assume cwd. Fetch first so the agent isn't building on a stale base.
- **Background the agents** so you stay free to coordinate; handle each completion as it arrives.
- **Set the issue's board `Status` to `In progress`** the moment you dispatch (§9) — that's how a coworker knows not to grab it. It's the board Status field, **not** a label (there is no `in progress` label). Look up the project item id for the issue and set its Status field to the `In progress` option using your board's API/CLI.
- **Self-contained prompt.** The agent has only its prompt + the repo. Use the dispatch checklist below.

### Agent dispatch checklist

Give every implementation agent:

- **Setup:** fetch `origin`; `git worktree add -b <branch> <path> origin/main`; operate inside it (`git -C` / explicit `cd`).
- **Context:** the repo, the issue number ("read it with `gh issue view`"), and any decisions already made (don't relitigate).
- **Conventions:** match existing code/test style; **tests required in the same PR**; **run the FULL CI-equivalent gate including lint** (not a subset — see §4); docs in the same PR as the change.
- **Git hygiene:** each git command a **separate call, never chained with `&&`**; commit message ends with the repo's required `Co-Authored-By` trailer.
- **Output:** open a PR against `main` with `Closes #N` (or `Addresses #N` if it only partially resolves the issue — don't auto-close); link the issue in a comment; **do NOT merge or tag reviewers** — a separate review pass + human sign-off + the queue handle that.
- **Report back:** branch, PR#, files changed, exactly what checks ran + results (and explicitly flag anything it *couldn't* run — e.g. sandbox-blocked DB tests), and any decisions/risks needing human judgment.

## 3. Review before queue — scaled to risk

A PR is not merge-ready just because CI is green. Dispatch a review whose depth matches the blast radius:

- **Security / authz / permissions →** adversarial bypass review. Prompt the reviewer to *break* it (enumerate every protected surface, try the bypass, default to "refuted" when unsure). This catches real horizontal-authz holes that CI sails past.
- **Tricky correctness logic →** a focused correctness review.
- **UI →** a design/a11y review against the mockups, but say plainly: **visual parity still needs a human on the deploy preview** — a headless agent can't see pixels.

Reviews exist to catch what CI structurally can't (see §4). Run them read-only; don't let a reviewer also be the implementer.

## 4. The false-green trap (the most important lesson)

**Green CI ≠ correct.** The recurring, expensive failure mode: tests that **mock or hand-fixture a boundary** verify the code against *the test's own assumptions*, not the real contract. When the real contract drifts — a DB `CHECK` constraint, an API response shape or column key, a schema default — the mock stays green while production breaks. In one session three PRs shipped green and were caught only by the queue's review: a feedback enum that violated a DB CHECK, a malformed-id that poisoned a transaction, a filter keyed on a column the API no longer emits.

So bias dispatch + review toward **anchoring tests to real contracts**:

- **At least one real-DB test per DB-touching handler** — run against the real test DB, exercising the actual schema, constraints, and column defaults. Not a mock/in-memory stand-in. This is what catches CHECK-constraint / NULL-scan / default-value bugs.
- **Frontend fixtures derived from the real API shape** (shared/generated types), never hand-written. A fixture must not be able to encode a response the API can't emit.
- **A thin contract/integration test at the seams** (FE↔API, API↔DB) beats unit tests on both sides of a mock.
- **Run the full gate, including lint.** A "typecheck + tests pass" report that skipped `lint` is how a lint failure reaches the queue.

When you review a PR, ask: *does any test here pass only because it mocked the thing that would actually fail?* If yes, that's the gap to close before queueing.

## 5. Verify + repeated-failure discipline

- **Confirm CI is actually green** (not just the agent's local claim) before adding the `merge-queue` label. If the agent was sandbox-limited and couldn't run a suite, **CI is the gate** — wait for it.
- **Rule out stale-checkout artifacts first.** A "failure" on a long-lived branch is often just staleness — `git fetch && merge --ff-only origin/main` (or rebase) and re-check before believing it. (A real example: an agent flagged a blocking "API discrepancy" that was purely an 18-commit-behind checkout.)
- **Second identical failure → stop and diagnose the root cause.** Don't blind-retry a third time; name the pattern, find why, and fix the source. (A flaky panic that recurred turned out to be a malformed-input query poisoning a shared transaction — a real latent bug, not a flake.)

## 6. Human sign-off + handoff

- **Never auto-merge, and never label `merge-queue` without the human's go.** Surface a **concise per-PR summary** — what it does, why, test results, any risk/flag — not a raw diff. Let them sign off per-PR or in batches.
- **Handoff = add the `merge-queue` label.** That label is the merge-queue skill's authorization to merge (and the "a deliberate act merges a PR" norm). Only add it once the PR is reviewed, green, and signed-off.

## 7. Handling bounces

The drainer (or a reviewer) will sometimes **bounce a PR back** — it removes the label and comments why (usually a must-fix that CI missed; see §4). When that happens:

1. Read the bounce comment for the exact defect.
2. Dispatch a **targeted fix** — and crucially, **add a test that anchors to the real contract** so the bug can't regress (the bounce is proof the existing tests were false-green).
3. Re-verify green, then re-add the `merge-queue` label.
4. **File non-blocking findings as their own issues** — file:line, enough detail to act on cold, labelled per §9. Don't let them bloat the current PR.

## 8. Sequencing to avoid churn

- **Order PRs that share files.** If two PRs both touch shared test fixtures, merge one first and let the other rebase — recommend the order to the human rather than queueing both blind.
- **Hold cross-cutting refactors** (e.g. extracting a shared component) until the PRs that *create their call sites* have merged, then dispatch the refactor against the settled tree. Dispatching it early means fighting moving files.
- **Let the queue's update-branch handle rebases** for already-labelled PRs; don't hand-rebase them out from under the drainer.
- **Bug-class burndowns arrive as batch sub-issues — treat them as normal Ready work.** A `systematic-bug-hunt` lands a detector *ratchet* first, then files a tracking epic + per-batch sub-issues (one PR's worth of files each). Pick them up like any other Ready issue: each PR fixes its batch, **lowers the ratchet baseline**, and `Closes` its sub-issue. Two things to expect: (1) the issue points at the detector as the live source — run it for current targets, don't trust hardcoded line numbers; (2) the ratchet is already in CI, so if one of your *other* PRs reintroduces the class (e.g. a migration re-adding a swallowed error), it fails on its own diff — fix it there. See the `systematic-bug-hunt` skill.
- **If a wide codemod PR is in flight instead (the no-orchestrator fallback), let it land first.** A single PR touching dozens of files is the expensive side to rebase; your narrow PRs are cheap. Land the sweep first and rebase onto it, or hold overlapping issues until it drains — watch for its declared scope in wherever your team tracks in-flight sweeps.

## 9. Board + label lifecycle — the board is the source of truth for coworkers

Other people (and other agent sessions) read the board to decide what to pick up. State has **two axes**: workflow position is the board **`Status` field**, gating reason is a **label**. Keep both honest so **`Status: Ready` always means ready**:

**Workflow position → board `Status` (not a label):**
- `Ready` → **truly actionable now, unblocked.** If it's blocked, it isn't Ready — give it a gating label and leave it at `Backlog`.
- `In progress` → set the moment you dispatch an agent; tells a coworker "we're on this, don't grab it." For **sliced/incremental** issues it stays `In progress` across the whole series — keep shipping the next slice (see §1) rather than treating it as hands-off — and only leaves `In progress` when the series is complete.
- `In review` / `Done` → driven automatically by the `merge-queue` skill (queued → In review, merged → Done). You don't set these by hand.

**Gating reason / handoff → labels:**
- `merge-queue` → reviewed + green + signed-off (the PR handoff to the drainer). Still a label — it's a PR signal, not a board column.
- `blocked:decision` → waiting on a human/product call. `blocked:dependency` → waiting on another PR/issue/code. `needs:setup` → waiting on a secret/account/config. `post-launch` → deferred past launch.

If you file follow-ups, triage them by the same rule (a runbook gated on a deploy is `blocked:dependency` at `Backlog`, not `Status: Ready`). When a teammate comes online mid-flight, do a quick board/label audit so their view is unambiguous.

## 10. Anomalies (they happen at scale)

- **Agent finished but opened no PR** (lost completion) → the branch is usually pushed; open the PR from it yourself.
- **Agent stalled** — uncommitted WIP, no completion after a long time → don't fight it; **re-dispatch fresh in a new worktree/branch** and orphan the old one (clean it up in the audit).
- **Silent/stalled agents accumulating** → that's the signal you've over-parallelized. **Consolidate: land what's ready before adding more,** and flag the pace to the human. More concurrency past a point just buys rebase churn through a serial queue.

## 11. End of session — save-audit

Before stopping: confirm nothing is unpushed or stranded (every branch pushed, every PR open-and-queued or merged), then **prune merged worktrees and their local branches**, keeping only the active ones. Force-remove orphaned/stalled worktrees whose work was superseded. A tidy worktree list is the fastest read on "what's actually still in flight."

## Notes

- Pairs with `merge-queue` — read that skill to understand the drain side and the exact label mechanics. This skill stops at the label; that one starts there.
- These are patterns, not rigid steps — scale the ceremony to the work. A one-line copy fix doesn't need an adversarial review; a permission change does. Use judgment about where the risk actually is.

## Living document

Update this skill when:
- The set of roles / terminals changes
- Dispatch or bounce-handling patterns evolve
- The board workflow it orbits changes
