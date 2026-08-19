# Board structure

The board is the source of truth. Everything else — the orchestrator, the merge queue, you — orbits it. This is the structure that keeps a board legible when a lot of work (human and agent) is moving through it at once.

## Three axes

An issue's state has **three independent axes**. Keeping them separate is what stops the board turning into label soup.

### 1. Where it is in the workflow → the board **Status** field (not a label)

```
Backlog → Needs human → Ready → In progress → In review → Done
```

Set this on the board itself. Do **not** create `ready` / `in progress` labels — the Status field already carries it, and two sources of truth drift apart.

- **Backlog** — filed, not yet actionable (or gated, see axis 2)
- **Needs human** — blocked on you specifically: a decision, a clarification, judgment
- **Ready** — actionable and unblocked; this is the queue the orchestrator pulls from
- **In progress / In review / Done** — driven as work moves (the merge-queue skill can drive In review → Done automatically)

### 2. *Why* it's gated → a **label**

A gated issue carries exactly one of these, and sits in `Backlog` until it clears:

| Label | Meaning |
|---|---|
| `blocked:decision` | Waiting on a human/product decision |
| `blocked:dependency` | Waiting on another issue, PR, or code dependency |
| `needs:setup` | Blocked only on a small human action (set a secret, provision an account/keys, flip a config) — agent-dispatchable the moment it's done |

An actionable, unblocked issue carries **no** gating label and sits at Status `Ready`.

### 3. *What area* it touches → a **`theme:*` label**

Give every open issue exactly one theme (e.g. `theme:payments`, `theme:growth`, `theme:platform`, `theme:security`, `theme:bugs-ux` — pick the set that matches your product). Now the board reads as a roadmap: group by theme and you can see where the work actually is.

## Optional fields

- **Priority** (`P0`–`P3`) and **Size** (`XS`–`XL`) as board fields, populated across open work, so you can sort by impact and estimate load. Optional, but cheap and high-value once you're running real volume.

## The rules

- **Change state → update the board and the labels together.** A decision lands → remove `blocked:decision` *and* set Status `Ready`. Work starts → Status `In progress`. Don't let them fall out of sync.
- **Triage at creation.** A newly filed issue gets a gating label if it's blocked/deferred, otherwise Status `Ready` (or `Backlog` if filed but not yet actionable). Untriaged issues are invisible work.
- **To find actionable work, read the `Ready` column** — not a label query. Ready is the single, honest queue.
- **Re-audit periodically against `main` / merged PRs.** Things ship or get resolved out-of-band without the issue being closed. Sweep for these, close them, and fix any mislabeled state — otherwise the board slowly lies to you.

## Why this matters more with agents

When you're the only one working, an informal board is fine. The moment you're running orchestrated agents, the board *is* the coordination layer: it's how the orchestrator knows what's `Ready`, how the merge queue reports what's `Done`, and how you keep judgment (`Needs human`) from getting lost in the throughput. Structure here buys you legibility everywhere else.
