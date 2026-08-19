# Fable audit prompts

Broad, structured audits you dispatch on a **capable, long-running model** (e.g. Fable) to sweep a codebase and produce a **filed, well-specified report** — findings detailed enough that **cheaper models can then execute the work**.

## The pattern

- **The expensive model audits; cheap models execute.** Run the broad sweep on a capable, long-running model — its job is to think hard and produce *well-specified* findings. Those findings then become work that smaller/cheaper models can carry out. You spend the expensive tokens once, on the thinking.
- **Ask for a report, split by concern.** A good audit prompt names the dimensions up front so the output is organized and actionable, not a wall of text.
- **Output gets filed**, not left in the chat — write it to a doc (e.g. `docs/audits/YYYY-MM-DD-<topic>.md`) so it's reviewable, diff-able, and each finding can become an issue for a cheaper model to pick up.
- **When it's useful:** when you have a nagging "I'm not sure our X is good enough" and don't want to grind through it by hand — test coverage, security, correctness, performance. High signal, and the output pays for itself as executable work.

---

## Example 1 — test coverage / reliability

> I'm not happy with our test coverage — we have gaps, and I'm not sure all the tests are validating what they should be. Look through this and put together an in-depth report highlighting strengths, weaknesses, and areas to invest in. Focus first on what's there, but where relevant you can also look at other forms of reliability coverage that would be good additions.

_Run the audit on the capable model; the filed report becomes work cheaper models can execute._

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
