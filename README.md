# AI Dev Starter Kit

A small set of Claude skills and templates for doing real engineering work with AI — the ones I actually use day to day, cleaned up to share.

If you want the thinking behind them first, start here: [Useful AI skills for engineering leaders](https://cate.blog/2026/06/09/useful-ai-skills-for-engineering-leaders/).

---

## Why these exist

Skills aren't prompts you paste. They're **encoded judgment** — the repeatable parts of how you work, written down once so the AI does them the same careful way every time, and so *you* spend your limited attention on the parts that actually need you.

The goal isn't to hand your thinking over. It's the opposite: offload the legwork, keep the judgment. A good skill makes the machine reliably do the boring, easy-to-skip, easy-to-get-wrong steps (checks, reviews, sweeps) so you can stay at the level where your judgment is the value.

---

## The model: a board + a few terminals

**The board is the source of truth.** Work is tracked as issues moving through a status workflow (roughly: `Backlog → Needs human → Ready → In progress → In review → Done`). Everything else orbits that. I wrote about running this setup in practice here: [Maturing our development process as an AI-first 2-person team](https://cate.blog/2026/07/21/maturing-our-development-process-as-an-ai-first-2-person-team/).

I typically run a few terminals in parallel, each with a role:

1. **Human (you)** — unblocking and clarifying. You own the judgment: what matters, what's ambiguous, what's "actually done." When the AI needs a decision or gets stuck, this is the loop.
2. **Orchestrator** — fans out and coordinates the work across the board (dispatches, tracks, keeps things moving).
3. **Merge queue** — serializes merges and does final validation before anything lands.

> On the merge queue: I run a **custom merge-queue skill because I'm not on GitHub Enterprise** (which has a built-in merge queue). If you *are* on Enterprise, this terminal can just do **final validation and then drop the PR into your standard/built-in merge queue** instead of the custom drainer. Same role, less machinery. What I find useful about it either way is having an **impartial gate that enforces standards consistently** — every PR gets the same checks, no matter who (or which agent) wrote it.

---

## What's in here

Each of these is a teaching version — adapt the specifics (repo, checks, board columns) to your own setup.

| Skill | What it's for | When it's useful |
|---|---|---|
| **eng-overview** | A standing read on your engineering: open PRs, recent merges, operational state | Start of day, or any time you want the state of the world without clicking through 12 tabs |
| **daily-product-review (PM)** | Reviews the product/board from a PM lens — what's shipping, what's stuck, what needs a decision | Daily planning; keeping the product moving, not just the code |
| **preflight** | The checks to run *before* a PR goes up (lint/tests/guards) so CI isn't where you find out | Every time, before you open or queue a PR |
| **CLAUDE.md (example)** | A worked example of a project `CLAUDE.md` — the always-loaded instructions that shape every session | Setting up a new repo; encoding your conventions so you stop repeating them |
| **trycycle** | An iterative build → test → review loop — [danshapiro/trycycle](https://github.com/danshapiro/trycycle) (public MIT) | Larger, more complex pieces of work with a tight feedback loop |
| **fable-audit-prompts** | Broad audit prompts to dispatch on a cheaper model, output filed as a report | When you have a nagging "is our X good enough?" — test coverage, security, correctness, performance |

**On trycycle specifically:** it lives at [danshapiro/trycycle](https://github.com/danshapiro/trycycle) — clone it directly. Feed it the **GitHub issue** (`gh issue view <n>`), not the chat transcript: its phases default to transcript placeholders, and a long session is noisy — the issue is the clean, canonical spec. Best for **larger, more complex pieces of work.**

---

## Further reading

The thinking behind all this, on [cate.blog](https://cate.blog):

- [Maturing our development process as an AI-first 2 person team](https://cate.blog/2026/07/21/maturing-our-development-process-as-an-ai-first-2-person-team/) — the orchestrator + merge-queue setup and board hygiene, in practice
- [Useful AI skills for engineering leaders](https://cate.blog/2026/06/09/useful-ai-skills-for-engineering-leaders/) — why skills, and how to think about them
- [The Value of Getting Closer to the Work](https://cate.blog/2026/06/23/the-value-of-getting-closer-to-the-work/)
- [High Throughput, Low Completion](https://cate.blog/2026/05/05/high-throughput-low-completion/) — shipping lots of PRs vs finishing things
- [Who's the Admin, Me or Claude?](https://cate.blog/2026/04/07/whos-the-admin-me-or-claude/)

## Coming next (v2)

More templates I'm sanitizing/writing up to add here: **orchestrator** and **merge-queue** templates, a generic **PR-review** skill, **bug-class hunting** (finding a whole *class* of bug, not one instance), **setting a ratchet** (lock in progress so regressions can't creep back), **fixing incrementally**, a **finding-something** worked example, and the full **board structure**.

---

## A note on using these

These are teaching examples, not a framework to adopt wholesale. Take the shape, throw away my specifics, and make them yours — the value is in the judgment they encode, and that part's up to you.

_— Cate ([cate.blog](https://cate.blog))_
