---
name: systematic-bug-hunt
description: >-
  Test-driven systematic bug hunt — when a single bug, smell, or deprecated pattern is suspected to recur across many files and you want the whole class fixed at once (not just the spot you noticed), land a generalized detector test that enumerates every instance and guards against regressions, then burn the sites down (one PR per batch via an orchestrator, or a single sweep) with the detector left behind as a standing CI guard. Signals — you want every occurrence found and fixed; want to sweep or migrate all call sites of an old helper/function/pattern to a new one; suspect half the handlers have the same problem; want to "fix the whole class", "track down the lot", or "stop it and make sure it can't come back". Also invoke by name ("systematic bug hunt", "bug-class hunt", "codemod this everywhere", "test-driven bug hunt"). Covers swallowed or unlogged errors, missing auth or validation, PII in logs, unsafe or un-interpolated strings, raw-SQL or deprecated-API migrations — any case where the same mechanical change repeats across dozens of sites. Skip for a truly isolated one-off (just fix it), a board of unrelated issues (use pr-orchestrator), or draining already-labelled PRs (use merge-queue).
---

# Systematic bug hunt

## The core idea

Most "fix this bug" requests are really "fix this *class* of bug." A handler that swallows its database error is rarely the only one — the same pattern is usually copy-pasted across dozens of call sites. Fixing the one you noticed leaves the other forty live, and you have no way to know you got them all.

The move that changes everything: **write a test that detects the bug class first, before fixing anything.** A good detector turns a vague hunt into a finite, verifiable list — it tells you exactly how many sites exist, which files, and (critically) when you're done. It is two artifacts in one: the **enumerator** that drives the work, and the **standing CI guard** that keeps the class from coming back.

This skill is the methodology for that: **detect → enumerate → burn down → leave the guard behind.** It scales one person to a 200-site cleanup while staying honest about correctness.

## When to use it (and when not)

Use it when the fix is **uniform and mechanical across many sites** — the same transformation applied in N places.

Don't force it when:
- It's genuinely a **one-off** — one site, no recurrence. Just fix it.
- Each site needs **bespoke judgment** — a detector can still *enumerate* them as a worklist, but don't pretend a codemod will do; treat the output as careful manual work.
- You're working a **board of unrelated issues** — that's `pr-orchestrator`. This skill is one class.

## Two shapes — pick by whether an orchestrator is running

The detector and the enumeration are identical either way; what differs is how you land the fixes.

- **Default — detector-first, then orchestrated burndown (§3–§6).** Land the detector alone as a *ratchet* PR, file a tracking issue + per-batch sub-issues, and let `pr-orchestrator` (or you, across sessions) chip the sites down one small PR at a time. Use this whenever an orchestrator is running **or the class is large**. It composes natively and avoids the collision a wide PR otherwise creates — a single PR touching dozens of files fights every narrow PR landing on those same files, getting bounced from the merge queue and letting concurrent work *reintroduce* sites. (This is not hypothetical: a wide sweep run against a live migration stream bounced twice and had fixed sites re-added in two handlers.)
- **Attach to an existing burndown (§3 + §4a).** When the class is *already* being worked — a tracked migration the orchestrator is steadily picking up (e.g. a raw-SQL → typed-query sweep) — don't re-file anything. Land **just the ratchet** and let the in-flight work ride it: each existing PR lowers the count, the ratchet stops the count rising. You're adding the *guard* a long-running migration was missing, not starting a burndown. This is the lightest-touch mode and often the real situation when an orchestrator is busy.
- **Fallback — one wide PR (§7).** Detector + every fix in a single PR via parallel subagents. Use **only** when nothing else is touching these files *and* the change is uniform enough to land at once.

The shared spine — the detector, regression-proof verification, the detector as your safety net — applies to all three (§ "Verification discipline").

## 1. Pick a bug that's actually a class

Start from a real bug — a tracked issue, an error-monitoring cluster, something just hit. Then ask: *is this a pattern?* Signals it is:

- The fix is "add/remove/change the same thing," not "redesign this."
- You can describe the bug as a grep-able or AST-able shape ("`httpError(w, 5xx, …)` with no logged cause", "API response includes an internal-only column").
- The codebase has many similar call sites.

If you can't write down the shape, you can't write a detector — and you probably have a one-off.

## 2. Write the detector — the centerpiece

The detector is the most valuable artifact you'll produce. Invest in it.

**Make it a real test in the repo's test suite**, not a throwaway grep — so it (a) runs in CI as a permanent guard and (b) is precise enough to trust. For structural patterns in typed languages, an **AST walk** (Go `go/ast`, TS compiler API, Python `ast`) beats regex — it sees scope, call structure, and types, so comments/strings/formatting don't fool it. For value/behavioral patterns, a **table-driven or property-based** test fits better. Pick the cheapest precise form.

**The detector must partition, not just match.** Almost every class has look-alikes that are *not* bugs. Example: `if err != nil { httpError(w, 500, "query") }` discards a real cause (bug), but `if h.DB == nil { httpError(w, 500, "no db") }` is a sentinel guard with no cause to log (not the bug). A detector that flags both is noise; one that silently counts sentinels as "must fix" sends agents to "fix" things that aren't broken. So:

- **Flag the real class** and fail on it.
- **Report the look-alikes separately as informational** — the *human-judgment bucket*, surfaced explicitly, never swept in.
- Make the partition criterion principled (e.g. "condition tests a local error variable `X != nil`" vs "compares a receiver field `h.Foo == nil`") so it generalizes beyond the examples you saw.

**Print the enumeration grouped by file** — file, count, short identifier per site. That output *is* the work plan.

**Fail-on-any vs ratchet — choose by which shape you're in.** The simplest detector fails whenever the count is `> 0`; that's right for the single wide PR (§7), where the test goes green exactly when the class is gone. But the default flow lands the detector *while sites still exist*, so it must be a **ratchet**: record the current baseline count and fail only when a change pushes it *higher*. A ratchet lands immediately on a repo that still carries the debt, freezes the debt from growing, and burns down as you lower the baseline — until 0, when it becomes the permanent fail-on-any guard.

Run it. The failing count is your ground truth — it sets the whole shape of the work.

## 3. Land the detector first — as a ratchet

Land the detector as its own small PR *before* fixing anything, baselined to the current count. Land it first because:

- **Its whole job is to guard the concurrent work.** The instant it's in CI, no new PR — yours or the orchestrator's — can add a site without going red *on its own diff*. The class can only shrink from here.
- It's **tiny and uncontroversial** — fast to review, lands quickly.
- It makes the count **official and visible** for the burndown to track against.

Keep the baseline as a named constant with a comment pointing at the tracking issue ("burn down to 0; see #<epic>").

## 4. Carve the worklist — tracking issue + batch sub-issues

File one **tracking issue** (the epic): the class, a link to the detector, the current count, the burndown rule (each PR lowers the baseline; at 0 the ratchet flips to fail-on-any), and the partition — the human-judgment bucket called out as possibly needing a product call, not a codemod.

Then file **one Ready sub-issue per file-batch** (group by area; size to roughly the orchestrator's concurrency cap so the board doesn't choke). Each sub-issue:

- names its files,
- says: "run the detector; fix the sites it reports in these files; lower the baseline by that many; `Closes #<sub>`,"
- **points at the detector as the live source** — never hardcode line numbers; they rot the moment `main` moves (every site shifts after an unrelated refactor lands).

Set the sub-issues to board `Status: Ready` — that's the column the orchestrator reads. Leave the epic at `Backlog`/tracking.

### 4a. ...unless the burndown already exists — then skip this step

If the class is already a tracked, in-flight migration (a checklist issue the orchestrator is steadily working), **don't re-file an epic and sub-issues** — you'd duplicate and compete with a queue that already exists. Land the ratchet (§3), add one comment to the existing issue explaining how the ratchet is maintained (a migration PR lowers the count; a regression fails on its own diff; tighten the baseline periodically), and stop. The in-flight work *is* the burndown; the ratchet just enforces its direction. (Real example: a raw-SQL → typed-query migration the orchestrator already owned — the right move was a tiny ratchet PR touching only the test + baseline, not 40 new sub-issues.)

## 5. Burn down — one batch per PR

The orchestrator (or you, across sessions) takes a batch sub-issue → one small PR. Each PR:

- fixes only its files — run the detector for *current* targets, apply the transform, flag any ambiguous site as human-judgment instead of guessing;
- **lowers the ratchet baseline** by the number fixed;
- verifies (§ "Verification discipline");
- `Closes #<sub>`.

Small PRs make rebases cheap — the wide-PR asymmetry that caused the churn is gone. And because the ratchet is already live, a *concurrent* PR that reintroduces a site fails *that* PR, not yours.

## 6. Close out

When the baseline reaches 0, the final burndown PR **flips the ratchet to fail-on-any** (the permanent guard) and the epic closes. Then **fix the source**, or the class re-enters through new code: update the convention doc (your repo's handler/coding conventions) and, if the orchestrator templates its agent prompts, that template — so new code uses the right pattern from the start. Detection (the ratchet) plus prevention (the convention) is what actually closes the class. Resolve or hand off the human-judgment bucket as its own decision.

## Verification discipline (all shapes)

- **The detector is your safety net — re-run it after every batch of edits.** It pinpoints exactly which sites were missed or done wrong, and (crucially) catches sites *reintroduced* by a merge from `main`. Trust it over your own diff-reading.
- **Confirm CI green from job status, not `gh run watch`.** `gh run watch --exit-status` can return 0 while required jobs are still in progress — it has reported a clean exit mid-run, nearly labelling a PR green early. Poll until the run's `status == "completed"` and read its `conclusion` (`gh run view <id> --json status,conclusion`), or check the live required-check states (`gh pr checks <n> --required`). Never label a PR `merge-queue` / mark it green off the watcher's exit code alone.
- **Build + vet + format.** A clean build proves the variables your edits reference are actually in scope — cheap, strong signal.
- **Regression-proof behavior-preserving changes.** The test failure set should be *identical with and without your diff*. Capture the suite, stash your changes, run on clean `main`, diff the two failure lists — the only delta should be your detector flipping. This separates "I broke something" from "already failing," and surfaces unrelated breakage (e.g. a stale local DB) so you don't misattribute it.
- **Subagents edit only — no git, no concurrent build.** Hand each explicit targets (not a hunt), the precise transform with a do-not-touch list, and "flag, don't guess." Verify centrally. The dispatch discipline (fit-the-window tasks, verify-once) is shared with `pr-orchestrator` — read it there.
- **Spot-check the diff shape.** A uniform codemod should look uniform; an outlier hunk is worth reading.

## 7. Fallback: the single wide PR (no orchestrator)

When nothing else is touching these files and the change is uniform, one PR is fastest:

- Batch the failing files into **non-overlapping** groups (the conflict unit is the file — never one agent per site, never two agents per file). Fan out parallel subagents (edit-only).
- Verify centrally (§ "Verification discipline").
- Converge into **one PR** with the detector — **fail-on-any** here, since everything lands together — as the guard. A reviewer trusts the test instead of eyeballing N near-identical hunks; one green transition, no red-`main` window.
- If `main` advances mid-flight and touches your files, merge it in and re-run the detector — it re-flags reintroduced sites; re-apply. *This churn is exactly why the orchestrated burndown (§3–§6) is the default when one's running.*

## How this pairs with the other skills

- **`pr-orchestrator`** runs a board of unrelated issues, one PR per issue. In the default flow above it's the *burndown engine*: it picks up the batch sub-issues you file (§4) and drives them through review + queue. It also carries the reciprocal note — let an in-flight sweep land first and rebase narrow PRs onto it.
- **`merge-queue`** is the serial drainer for labelled PRs. This skill (and the orchestrator) end where it begins: reviewed, green, labelled. The label is the handoff.

## Living document

Update this skill when:
- A new class of bug recurs and needs its own hunt pattern
- The ratchet mechanism changes (a new guard/check to lock in progress)
- You find a better way to scope "the whole class" or drive the incremental fix
