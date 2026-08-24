---
name: daily-product-review
description: "Daily product review and board hygiene. Use this skill for product review, daily standup review, board check, channel scan, or anything like 'what's new', 'pull updates', 'check the channels', 'anything untracked', 'is everything up to date', 'run the morning review', or 'what needs attention on product'. Also trigger when asked to create tasks from chat messages, cross-reference standups with the board, or check for untracked requests."
---

# Daily Product Review

Run the daily product review for a product team. This skill scans chat channels and a task board to surface untracked work, flag stale items, and keep the board in sync with what's actually happening.

## Required tools

- Chat (read channels, read threads, search) — e.g. Slack, Discord
- Task board (fetch, search, create tasks, update tasks, add comments) — e.g. Notion, Linear, Jira

## Channels to scan

Configure for your team. Typical pattern:

- **ad-hoc-asks channel** — where ad-hoc requests come in; may have automation auto-creating tasks for messages with a prefix
- **bugs channel** — bug reports and feature requests; usually manual triage
- **dev-standup channel** — daily engineering priorities
- **product-general channel** — product updates, demos, mockups, feedback requests; scan for work that should be reflected on the board and for feedback asks that may need a follow-up

### Out of scope (don't scan)

- Dormant channels
- Private project-scoped channels (only scan if explicitly asked)
- Non-product channels (talent, growth, marketing, company-wide)

## Task board

- **Roadmap board** — typical statuses: Idea, Backlog, Next Up, In Progress, Urgent, Pending Feedback, Done. Properties: Milestone, Assignee.
- **Bugs and Ad-Hoc board** — typical statuses: Pending, In Progress, Urgent, Done. Properties: type (Ad-Hoc or Bug), Priority, Description.

## Team context

Note who the frequent posters are and their roles (engineers, CEO, CS, etc.). The skill should know who's expected in the standup channel.

## The review process

### Step 1: Determine the lookback window

- Default: last 5 working days. Longer than a single day so nothing slips through if a run is missed or after PTO.
- Skip weekends in the calculation.
- If asked for a specific window ("yesterday", "this week", "since Monday"), use that.

### Step 2: Scan ad-hoc-asks channel

1. Read all messages since the lookback window
2. **ALWAYS read thread replies on every message before flagging it.** Asks are sometimes resolved, clarified, or deemed irrelevant in the replies. If the thread resolves the ask, skip it.
3. Identify messages that are requests but did NOT match any automation prefix — these get missed
4. For messages that DID match the prefix, verify a task was created on the board by searching for matching keywords
5. For each untracked request: note who posted it, what they're asking for, and recommend whether to create a task

### Step 3: Scan bugs channel

1. Read all messages since the lookback window
2. **Read thread replies before flagging.**
3. Identify bug reports and feature requests
4. Cross-reference with the ad-hoc board to check if already tracked
5. Flag anything that needs a task

### Step 4: Scan product-general channel

1. Read all messages since the lookback window
2. **Read thread replies before flagging.**
3. Look for: WIP demos or mockups, explicit feedback requests, and updates that imply work being done
4. Cross-reference with the roadmap board — if someone says they're working on or shipped X, check it's reflected in the right status
5. If a feedback request is open and unanswered, flag it (the corresponding board item may need to move to Pending Feedback)
6. Don't double-flag items already surfaced by the standup channel

### Step 5: Cross-reference dev-standup with the board

1. Read recent standup posts
2. If someone says they're working on X, check whether X is marked "In Progress"
3. If someone says something is done, check it's marked "Done"
4. Flag mismatches
5. Don't flag missing standups on weekends
6. Don't flag missing standups for people who are out/on leave

### Step 6: Flag items needing attention

- Anything marked "In Progress" or "Urgent" that hasn't been updated in more than a week
- Anything with high priority that's still open
- Any items where board status doesn't match what's happening in chat

## Output format

Actionable checklist organized by section, with task links where possible. Keep it scannable — target under 3 minutes to read. Flag the most urgent items first.

If everything looks clean, say so briefly. Don't pad the output.

## When asked to create tasks

When creating tasks on the ad-hoc board, include:
- **Name**: prefixed with "ASK:" if it came from a chat ask, or "Bug:" for bugs
- **Type**: "ad-hoc" or "bug"
- **Description**: who asked, when, what they need, and the chat permalink
- **Priority**: match the urgency from the message
- **Status**: Pending (default)

When creating tasks on the roadmap board, include:
- **Name**: descriptive
- **Description**: context, dependencies (Blocked by: ...), references
- **Type**: feature or infrastructure
- **Milestone**: if applicable
- **Status**: Backlog (default)

## When updating the board

- When moving items to Pending Feedback, add a note explaining what feedback is needed
- When something is resolved or irrelevant, mark it Done with a note explaining why

## Key gotchas

- Automation prefixes are often case-sensitive and may miss messages even when they appear correct. Always verify.
- Some frequent posters skip the prefix entirely — know who.
- Channels without automation need manual triage on every scan.
- Automated bots posting in channels may be real signal (e.g. user feedback bots) — treat accordingly.
- Standup reminders may fire on weekends — don't flag weekend gaps.

## Living document

Update this skill when:
- The board/product surfaces change (new stages, new sources of truth)
- A new signal matters for the PM read (a metric, a stuck-state, a decision type)
- Your planning cadence shifts
