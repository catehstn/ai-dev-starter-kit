---
name: engineering-overview
description: Use this skill for engineering oversight — surfacing operational fires (Sentry, deploy failures), open PRs needing attention, recently merged PRs to be aware of, blocked design questions (schema/authz/spec), in-flight issues, backlog by impact, and roadmap items needing attention now. Trigger on "engineering status", "what's happening in eng", "engineering overview", "state of play", any oversight question about the platform, or when planning mode is reviewing engineering work. Co-managed via a shared-skills repo; usable by anyone with engineering oversight responsibilities.
---

# Engineering Overview

## Purpose

Surface engineering priorities for daily/weekly planning. Strategic surfacing, not autonomous execution. Single source of truth in a shared-skills repo; symlinked into each user's local Claude skills directory.

## Scope

Engineering: API, web, schema, authz, deploys, observability, related tooling. Cohort of repos:

- Main monorepo (api + web)
- `.github` — shared engineering guidelines (CLAUDE.md)
- `shared-skills` — this repo
- `pm-template` — per-developer tactical PM template

**Out of scope** — don't surface here:
- Marketing, sales, customer success
- Cost reviews, security configs, 2FA — sensitive items live in personal session logs
- Hiring pipeline — has its own skill if relevant
- Per-developer tactical work — that's `pm-template` instances

## Priority hierarchy

When surfacing, always order by this hierarchy. Higher tiers beat lower tiers regardless of count.

1. **Operational fires** — anything broken right now (Sentry errors, deploy failures, CI red on main). Drop everything.
2. **Open PRs needing attention** — review requested, CI failing, age >3 days. Open PRs go to top of list, they outrank new work.
3. **Recently merged PRs to be aware of** — substantial merges in the last 24–48h that warrant a glance for context, scope drift, or stale cross-references. Not every merge — just non-trivial ones.
4. **Blocked design questions** — schema/authz/spec issues blocking implementation. When these aren't moving, downstream PRs park.
5. **In-flight issues** — tracked work in progress on the project board.
6. **Backlog** — issues filed but not started. Surface top items by impact.
7. **Future** — roadmap items, post-launch work. Only surface if timelines are getting tight.

## State sources

| Source | Access | Surfaces |
|---|---|---|
| GitHub (main repo) | gh CLI / API | PRs, issues, project board, CI state |
| GitHub (.github) | gh CLI / API | Workflow rule changes |
| Deploy provider | PR check rollup or API | Web deploy state |
| Sentry / error tracker | API or MCP | Operational fires |
| Notion / docs | MCP if available | Specs, planning docs, design docs |
| Chat (Slack/Discord) | MCP if available | Async coordination, blockers, oncall items |
| Email | MCP if available | Customer-facing alerts, contractor comms |
| `shared-skills/shared/waiting.md` | local file | Cross-collaborator waiting list |

## Audit (when explicitly asked for status)

Run in this order. Stop early if operational fires demand attention. Always specify the target `--repo` on `gh` commands.

1. **Operational check.** Pull recent errors from the last 24h. Check deploy state via the most recent merged PR's check rollup; check CI on main. If anything failing, surface FIRST.

2. **Open PRs.**
   ```bash
   gh pr list --repo OWNER/REPO --state open --json number,title,author,createdAt,reviewDecision,statusCheckRollup,reviewRequests
   ```
   For each: author, age, CI state, review state. Flag tagged-for-review, failing CI, or older than 3 days. Cross-reference body against current state — if it references parked commits or follow-ups, verify they're still accurate.

3. **Recently merged PRs to be aware of.**
   ```bash
   gh pr list --repo OWNER/REPO --state merged --limit 25 --json number,title,author,mergedAt,additions,deletions
   ```
   Filter to merges in the last 24–48h. Flag any of:
   - Large diffs (>500 lines) that warrant a look-at
   - Scope-creep patterns (mockup PRs that swap shared components, refactor riding alongside feature work)
   - Stale cross-references in the body (sibling commits already merged, follow-ups already filed)
   - Missing tracked follow-ups (PR mentions "Phase 2" or "follow-up" with no issue number)
   
   Don't list every merge. Only ones worth attention.

4. **Blocked design questions.** Pull issues with `design`, `spec`, or `blocking` labels. For each: open question, who's blocked on whom, what's needed to unblock.

5. **In-flight.** Project board "In Progress" column. Per item: who, next step, blockers.

6. **Backlog.** Top 3 by impact. Anything blocking a launch or external commitment surfaces regardless of ranking.

7. **Future.** Items scheduled for next phase. Only surface if timelines are getting tight.

Format as scannable groups. Lead with operational if any, otherwise open PRs.

## Triage rules

- **Operational always wins.** Even mid-conversation, surface a Sentry alert immediately.
- **Open PRs > new work.** Don't suggest starting new work when a PR is sitting unreviewed.
- **Recently merged > new work, when something's worth flagging.** A large merged PR is a higher-leverage thing to look at than picking the next backlog item.
- **Blocked-design > in-flight.** A design question blocking multiple downstream PRs is higher leverage than nudging one in-progress task.
- **Cross-reference staleness.** When surfacing PRs (open or merged), check the body for cross-references that may be stale. If found, flag.
- **Don't drown in backlog.** Top 3 only unless asked for more.
- **Don't editorialise.** Surface, prioritise, don't soapbox.

## Coordination

- Joint decisions go in `shared-skills/shared/decisions.md` with date and outcome.
- Items one collaborator is waiting on another for go in `shared-skills/shared/waiting.md`.
- When the audit surfaces something needing joint input, flag it as "needs alignment" rather than assigning to one person.
- Don't auto-draft anything to contractors, customers, or external parties. This skill surfaces, doesn't write.
- This skill does NOT write code. Code-writing is the user's main Claude session work, not an oversight concern.

## Voice and tone

Direct, no fluff:
- No corporate framing
- Surface and prioritise; don't editorialise
- When something is genuinely urgent, say so plainly

## Non-goals

- Does NOT autonomously send anything (PRs, comments, emails, chat messages)
- Does NOT manage marketing, sales, customer business decisions
- Does NOT replace dedicated drafting skills
- Does NOT make decisions that should be joint
- Does NOT write code

## Living document

Update this skill when:
- Monitoring / observability is wired up (replace pending section)
- New external sources of truth come online
- Triage patterns emerge from real audits
- Coordination protocol shifts
