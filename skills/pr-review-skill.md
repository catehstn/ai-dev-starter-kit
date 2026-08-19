---
name: pr-review
description: Review a merged or open PR for real defects — verify correctness, security (authz / PII / secrets / XSS), tests, and data-integrity, then report structured findings with a clear verdict. Trigger on "review this PR", "review the merged PRs", "do a PR review round", "check this change". NOT for merging or queuing PRs (that's the merge-queue skill) or dispatching implementation work (that's the pr-orchestrator skill).
---

# PR Review

## Purpose

Catch the real issue, don't narrate the diff. **The value is in confirming the one thing most likely to be wrong** — a NULL-scan, a missing authz gate, a wrong scope, a leaked secret — not in describing what the PR does. A review that summarizes the change but misses the bug has failed even if every sentence is true.

**Verify the risky thing; don't just read it.** Where you can, run the test, check the schema, trace the auth path. Reading a diff tells you what the author intended; running it tells you what actually happens.

## Scope & boundaries

- **DO:** review the diff for correctness, security, tests, and data-integrity; assign a verdict; report tagged findings; file follow-ups worth tracking.
- **DON'T merge or queue PRs.** That's the `merge-queue` skill. If this PR is already merged, the review is awareness + cleanup, not a gate.
- **DON'T dispatch implementation work** — that's `pr-orchestrator`.
- Run **read-only**. Don't modify files as part of reviewing (resolving conflicts to unblock an *open* PR is a separate, explicitly-scoped task).
- Don't defer to the author's own PR description or implementation report. Treat it as claims to verify, not findings to transcribe. If your evidence conflicts with it, dig until you can explain the conflict.

## Review rubric — verify each

Not every item applies to every PR; match the checklist to the blast radius. A one-line copy fix doesn't need an authz audit; a permission change does.

### Correctness
- Does the logic do what the PR claims? Trace the non-obvious path, not just the happy path.
- **Nullable data scanned into a non-nullable type** — a nullable DB column read into a non-nullable value (Go `string`/`bool`/`int`/`time.Time`, a non-optional field in any typed language) blows up on NULL. Fix: coalesce at the query (`COALESCE(col, '')`) or use a nullable type. Watch `LEFT JOIN`s — they make even NOT-NULL columns nullable in the result.
- Column/scan alignment: the columns selected line up with the fields scanned, in order and type.
- Missing edge cases: empty input, zero rows, boundary values, concurrent access.

### Security
- **Authz / scoping.** Every privileged route enforces an actual permission check — not merely "is the user logged in" or "is the user this portal type." Entry-type checks are not authorization. Resource-scoped operations (edit/delete/manage *this* record) must verify the caller owns or may act on *that specific resource*, after the existence/404 check. Results must be scoped to the caller — no cross-tenant / cross-user / cross-company leak. For anything auth-touching, review adversarially: enumerate every protected surface and try to bypass it; default to "not proven safe" when unsure.
- **PII in logs.** No emails, names, tokens, or other personal/sensitive data written to logs or error messages.
- **Secrets.** No credentials, API keys, or tokens committed in the diff (source, fixtures, config, or test files).
- **XSS / injection.** User-controlled data is escaped/parameterized — no un-interpolated SQL strings, no raw HTML injection, no `dangerouslySetInnerHTML` on unsanitized input.

### Data integrity
- Schema/migration changes are consistent with the code that reads them; migrations are reversible or the forward-only choice is deliberate.
- Constraints (CHECK, NOT NULL, unique, foreign keys) match what the code assumes it can write.
- Transactions wrap multi-statement writes that must be atomic; a malformed input can't poison a shared transaction.

### Tests
- **Tests land in the same PR as the change.** A behaviour change with no test is a hold.
- Coverage matches the risk: happy path **plus** the scoping/no-leak case **plus** the null/empty-field case for data-touching code; the end-to-end flow for UI changes.
- **No skipped, weakened, deleted, or loosened tests.** A test skipped "because of the environment" or an assertion quietly relaxed to pass is a blocking issue, not a footnote. Run the suite yourself and check.
- **Watch for false-green tests** — a test that mocks or hand-fixtures the exact boundary that would fail in production verifies the code against the test's own assumptions, not the real contract. Ask: *does this test pass only because it mocked the thing that would actually break?* Prefer fixtures derived from real/generated types and at least one test against the real dependency (real test DB, real API shape) over mocks on both sides of a seam.

### Frontend (if applicable)
- Composed components over inline duplication; theme/design tokens over hardcoded colors; shared constants over magic values.
- No hydration hazards (non-deterministic values like `new Date()` / locale formatting rendered on both server and client).

## Verdicts & findings

- **Verdict:** `APPROVE` / `APPROVE-WITH-NOTES` / `CHANGES-NEEDED`.
- **Tag every finding:** `[BLOCKER]` (must fix before merge / must follow up) / `[SHOULD-FIX]` (real, but not merge-blocking) / `[NITPICK]` (discretionary).
- **Separate must-fix from suggestion.** Frame nitpicks as discretionary, not prescriptive. Push back on weak findings rather than padding the list — a review's credibility comes from signal, not volume.
- If you find one real issue, look harder — defects cluster. Keep investigating until you're confident you've found them all.

## Filing follow-ups

For anything `[SHOULD-FIX]` or above worth tracking beyond this PR:
- **Dup-check first** — search open issues before filing; add to an existing tracking issue rather than opening a duplicate.
- Reference the PR + `file:line`, with enough detail to act on cold.
- **Ask before filing security-sensitive or high-impact items** — some findings (auth config, secrets exposure, cost) should go to a private channel, not a public tracker. Confirm where before you file.

## Output

Lead with a **compact verdict table** (`PR | verdict | one-liner`). Then call out **only** the `[BLOCKER]` / `[SHOULD-FIX]` items and anything filed — signal, not diffs. Keep it tight. End with anything awaiting a human decision.

If you emit machine-readable output, return a single structured object: a `status` (`no_issues` / `issues_found`), a short `summary`, and an `observations` array where each entry carries `severity`, `category` (correctness / security / edge_case / missing_test / data_integrity / behavior / other), `expected`, `observed`, a `where` (file / line / symbol), and `evidence` (the exact read-only commands you ran and their relevant output). Preserve real evidence over advice; never invent command output you didn't actually see.

## Failure investigation

When a check or test fails, treat the failure as a clue about the system, not a result to transcribe. Characterize its *shape* before labelling it: read the assertion, the nearby tests, the changed files, and cheap focused reruns. Don't stop at "flaky" or "environmental" unless you can explain why that label follows from the evidence and what the next round should do about it. A stale local checkout or a stale local test DB is a common false failure — rule that out (`git fetch`, refresh the schema) before attributing a failure to the diff.
