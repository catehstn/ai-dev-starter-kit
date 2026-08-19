# Fable audit prompts

Broad, structured audits you dispatch on a **cheaper/capable model** (e.g. Fable) to sweep a codebase and produce a **filed report** — not a chat you have to babysit.

## The pattern

- **Ask for a report, split by concern.** A good audit prompt names the dimensions up front so the output is organized and actionable, not a wall of text.
- **Output gets filed**, not left in the chat — write it to a doc (e.g. `docs/audits/YYYY-MM-DD-<topic>.md`) so it's reviewable, diff-able, and you can turn findings into issues.
- **Dispatch on cheaper models.** These are wide, mechanical sweeps — they don't need your most expensive model. Run them cheap and in parallel.
- **When it's useful:** when you have a nagging "I'm not sure our X is good enough" and don't want to grind through it by hand — test coverage, security, correctness, performance. Low cost, high signal, easy to make a habit.

> Tip: if you find yourself putting off a broad audit because you're busy, that's exactly the moment to dispatch one — the cost of asking is tiny and the report often surfaces things you'd never have gone looking for.

---

## Example 1 — test coverage / reliability

> I'm not happy with our test coverage — we have gaps, and I'm not sure all the tests are validating what they should be. Look through this and put together an in-depth report highlighting strengths, weaknesses, and areas to invest in. Focus first on what's there, but where relevant you can also look at other forms of reliability coverage that would be good additions.

_Output → filed as a report. Dispatch on a cheaper model._

---

## Example 2 — codebase audit, split by concern

> Audit the codebase and generate a report, split by concern:
>
> 1. **Security — auth/session** (proxy, auth flows, invite tokens, redirects)
> 2. **Security — general** (XSS, uploads, secrets, headers, telemetry PII)
> 3. **Correctness — data layer** (API clients, mappers, hooks, contexts)
> 4. **Correctness — pages/UI** (flows, forms, server/client boundaries)
> 5. **Performance** (fetch waterfalls, rendering, bundle, caching)

_Each concern is its own filed section. Adapt the sub-bullets to your stack._

_(Do not, as I once accidentally did, also have it running your merge queue 😉)_
