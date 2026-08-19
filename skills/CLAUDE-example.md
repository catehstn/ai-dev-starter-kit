# Claude Code Guidelines for DRI Your Career Platform

## Issue Tracking

**If a problem is raised but not fixed in the current session, file a GitHub issue.**

- When the user mentions a bug, missing feature, or improvement and the conversation moves on without a fix, open an issue before the session ends
- Include enough context in the issue body (affected files, root cause if known, suggested fix) so it can be picked up later

**When the user provides a design handoff (HTML file, Figma link, screenshot, or markdown spec), always file a GitHub issue to track it** — even if you implement it immediately. The issue should link to or summarize the handoff, reference the relevant files, and be added to the project board. This ensures the handoff is traceable and can be revisited if the implementation drifts.

## Updating Module Content

Module content lives in `content/modules/` as markdown files. Each file has a YAML front matter block with these fields relevant to exercises:

- **`googleDocUrl`** — the URL of the Google Docs workbook participants open. Update this when a new version of the workbook is created. Use the base doc URL without heading anchors (e.g. `https://docs.google.com/document/d/DOC_ID/edit?tab=t.0`).
- **`exercises`** — a list of `title` + `description` pairs shown in the UI below the workbook button. Descriptions should be **concise 1–2 sentence summaries** of what the exercise asks — enough for a participant to understand the prompt without listing every sub-question. See module-2.md for the reference style.

The full exercise content (detailed prompts, sub-questions, values lists, etc.) lives in the Google Doc workbook and in `~/git/dri_course_development/<course>/0N-*/exercises.md`. The deployed descriptions are intentionally shorter. Optional exercises (marked as optional in exercises.md) should be omitted from the `exercises` list entirely.

If the user refers to a module without specifying the course (e.g. "module 3"), ask which course they mean: DRI Your Career (`module-N.md`), EM Survival Guide (`em-module-N.md`), or Navigating the AI Shift (`ai-module-N.md`).

### Syncing module body content from dri_course_development

When a PR merges in `dri_course_development` that changes a `module.md` file, use the sync script rather than manually diffing and editing:

```bash
cd ~/git/dri_course_development
./scripts/sync-to-platform.sh --course em   # or dri, ai, or omit for all
```

This preserves the frontmatter in each destination file and replaces the body from the source repo, then creates a PR. The local `dri_course_development` repo must be up to date (`git pull`) before running.

### Updating exercises for a module

1. Update `googleDocUrl` if the workbook doc has changed.
2. Rewrite each `description` as a short summary matching the module-2 style. Omit optional exercises.
3. Run `npm run sync-modules` locally to verify the content syncs without errors, then open a PR.

## Production Database

**Never write to the production database when a PR can accomplish the same thing.**

- Content changes (modules, exercises, etc.) → update the markdown file and open a PR; the deploy pipeline runs `sync-modules` automatically
- Schema changes → write a migration and open a PR
- Only write directly to production DB for things that genuinely cannot be done via a PR (e.g. one-off data fixes with no code equivalent, urgent hotfixes where a deploy would be too slow)

## Code Quality Principles

### DRY (Don't Repeat Yourself)
For components and larger code structures like entire pages, always refactor to reduce duplicate code that needs maintenance separately.

**When to refactor:**
- When you notice identical or nearly identical JSX being rendered in multiple places
- When data fetching logic is duplicated across pages
- When business logic is copy-pasted between components

**How to refactor:**
- Extract shared UI into reusable components
- Move shared data fetching into server components that can be reused
- Create utility functions for common operations

**Example:**
Instead of duplicating the multi-course catalog view in both `/` and `/courses`:
```tsx
// Before: Duplicated in both pages
// Root page and courses page both had ~100 lines of identical JSX

// After: Shared component
// Created src/components/courses/MultiCourseCatalog.tsx
// Both pages now use <MultiCourseCatalog />
```

This makes the code:
- Easier to maintain (single source of truth)
- Less error-prone (changes only need to happen in one place)
- More readable (clearer intent)

## Hydration (Server/Client Timezone Mismatches)

**Any value that depends on `new Date()` or `.toLocaleDateString()` will differ between server (Vercel UTC) and browser (local timezone).**

- Vercel runs in UTC; users in BST, ET, etc. will see different dates/statuses
- This causes React hydration mismatches that can make client components non-interactive

**Rules:**
- Add `suppressHydrationWarning` to any element that renders a `new Date()`-derived or `toLocaleDateString()`-derived value
- Never call `new Date()` inline during render for display purposes without this prop
- Use `/hydration-audit` (a custom slash command in `.claude/commands/`) to scan for unprotected instances

**Long-term fix:** replace `toLocaleDateString()` calls with a shared UTC-safe formatter rather than accumulating `suppressHydrationWarning` patches. See jyhsu/driyourcareer#97.

## Parallel Pages

The three course landing pages (`/dri-your-career`, `/em-survival-guide`, `/navigating-the-ai-shift`) and their route files are intentionally parallel in structure. When fixing a bug or adding a feature to one, always check and apply the same change to all three.

## Replacing Components or Pages

**Before replacing a component or page with a new one, audit what the old component does and account for every feature.**

For each capability in the old component, the PR must either:
1. Carry it forward in the replacement, or
2. Explicitly flag it as intentionally dropped with user sign-off

**Why:** The May 2026 landing page redesign replaced `CohortSelector` (which had group/bulk purchase registration) with `EnrollCard` (which did not), silently dropping bulk purchase from all three landing pages. The spec described what to add, not what to preserve — and no audit caught the gap.

This applies to component replacements, page rewrites, and any PR that removes a file that was previously rendering user-visible functionality.

## Documentation

### Keep docs in sync with code changes

When making changes that affect documented workflows, update the relevant doc in `docs/` in the **same PR** as the code change.

**What to update:**
- Adding or removing fields/props → update any doc that references them
- Adding a new shared component → add it to the shared components table in `docs/creating-a-new-course.md`
- Changing a process (e.g. how courses are created, how modules work) → update `docs/creating-a-new-course.md`
- Changing public routes, middleware, or auth → update relevant docs

## Always open a PR for code changes

**Never commit code changes directly to `main`.** Every code change — even a one-line fix — must go through a feature branch and a pull request.

Default workflow at the start of any code change:
1. Check the current branch with `git status`. If it's `main`, create a feature branch first: `git checkout -b <type>/<short-description>` (e.g. `fix/remove-participant-scope`, `feat/audio-progress-export`).
2. Make the edits on that branch.
3. Commit, push with `-u`, and open a PR targeting `main` via `gh pr create`.
4. Only merge after the user has had a chance to review (or has explicitly said to merge), and after `rm -rf .next && npm run build` passes.

This applies even when the user says "go ahead" or "ship it" — interpret that as "open the PR," not "commit to main." If you've already started editing on `main` by mistake, stop, create a branch, and move the changes there before committing.

Exception: docs-only changes the user explicitly asks to commit directly (e.g. "just push this CLAUDE.md update to main") are fine, but ask first if it isn't obvious.

## PR and Issue Workflow

### Link PRs to issues

When opening a PR for work that addresses a GitHub issue, always:
1. Include `Closes #N` (or `Fixes #N`) in the PR body so GitHub auto-closes the issue on merge, **and**
2. Post a comment on the issue referencing the PR: `gh issue comment <N> --repo <owner/repo> --body "PR opened: <owner/repo>#<PR>"`

If the issue is in a different repo (e.g. `jyhsu/dri_course_development`), use the full `owner/repo#PR` reference in the comment.

### Dispatch a review agent when a PR is created

**Immediately after opening a PR, dispatch a review agent** — do not wait until merge time.

Use the `Agent` tool with a prompt that includes:
- The full diff (`git diff origin/main...<branch>`)
- The problem being fixed and the approach taken
- A request to review for correctness, edge cases, missing tests, and any other issues

Address all significant findings before enabling auto-merge or merging. Nits can be skipped; correctness and edge-case issues must be fixed.

## PR Descriptions

**Always update the PR title and description when pushing significant changes to an existing PR.**

When a PR gains new scope (new files, new features, expanded content), update both the title and description before asking for review or merge. Use `gh pr edit <number> --title "..." --body "..."` to update them.

## PR Merging

### Always verify CI is green before merging

**Never merge a PR while CI is red or in progress.** Branch protection requires `test` and `e2e` to pass before merging — GitHub will block the merge if they are red.

Before running `gh pr merge`, always run:

```bash
gh pr checks <number> --repo jyhsu/driyourcareer --watch
```

Only proceed once all required checks show `pass`. If a check is still `pending`, wait for it. `--auto` is safe to use since branch protection is enabled.

### Always check if a branch has been merged before committing to it

Before committing to a feature branch, verify it hasn't already been merged:

```bash
gh pr list --state merged | grep <branch-name>
# or
gh pr view <number> --json state
```

If already merged, create a new branch from `main` instead.

### Always verify base branch before merging

Before recommending or merging any PR, check that it targets `main`:

```bash
gh pr view <number> --json baseRefName
```

If it targets another branch (stacked PR whose base already merged), retarget it first:

```bash
gh pr edit <number> --base main
```

**Why:** Stacked PRs target their parent branch. When the parent merges to `main`, GitHub marks the child as "merged" into the parent — but those changes never reach `main`. This happened with PRs #42 and #43, which required a recovery cherry-pick (PR #48).

## Database Design Principles

### Prefer hardcoded constants over DB tables for uniform config

Before creating a new Prisma model / DB table, ask: **does this value genuinely need to vary per record, and does it need to be editable at runtime by a non-engineer?** If not, a hardcoded constant in `src/lib/` is simpler and has no failure modes.

**Example:** Bulk discount tiers were initially stored as a per-cohort `CohortBulkDiscount` table, but the tiers were always the same across all cohorts. The right solution was `STANDARD_BULK_DISCOUNTS` in `src/lib/bulk-discounts.ts`. The DB table added complexity, a risky write pattern on every admin save, and caused a local DB corruption (PR #166).

A DB table earns its place only when values genuinely differ per record **and** need runtime editing by non-engineers.

### Never use deleteMany + createMany outside a transaction

Replacing a collection with `deleteMany` then `createMany` is two separate operations — if the second fails, the data is gone. Always wrap in a transaction:

```ts
await prisma.$transaction([
  prisma.someRelation.deleteMany({ where: { parentId: id } }),
  prisma.someRelation.createMany({ data: newItems }),
])
```

Or better: use per-item `upsert` + delete-obsolete to avoid the drop window entirely.

## Build & Deployment Workflow

### IMPORTANT: Only build before production deployments

**Development Workflow:**
- Make changes without running builds after each edit
- This significantly speeds up the development process
- Trust TypeScript in your editor for immediate feedback

**Production Workflow:**
When ready to push to production:
1. Clean the build cache: `rm -rf .next`
2. Run full build: `npm run build`
3. This catches TypeScript errors and other issues
4. Only push if build succeeds
5. Commit and push: `git add . && git commit && git push`

**Rationale:**
- Running builds after every change is too slow (can take 1-2 minutes)
- Build verification is only needed before deployment
- TypeScript and other errors will be caught in the final build before pushing

## Claude Code Skills

Install these Vercel-published skills globally to get Next.js and React best-practice guidance inline:

```bash
npx skills add vercel/next-best-practices -g   # App Router, server components, Vercel deployment
npx skills add vercel/react-best-practices -g  # React hooks, performance patterns
```

Both are relevant: the Next.js skill covers framework/deployment specifics, the React skill covers general component patterns.

## Project Overview

Next.js 15 (App Router) course platform. Participants enroll in cohorts, work through modules with exercises, and get coach feedback. Multiple courses supported (DRI Your Career, EM Survival Guide).

**Stack:** TypeScript, Prisma + Neon PostgreSQL, Clerk auth, Stripe payments, Resend emails, Tailwind CSS 4. Deployed on Vercel.

## Common Commands

```bash
npm run dev                  # Start dev server
npm run build                # Production build (migrations + sync + next build)
npm test                     # Unit tests (vitest, watch mode)
npm run test:run             # Unit tests once
npm run test:e2e             # E2E tests (Playwright)
npm run sync-modules         # Sync markdown content to database
npm run lint                 # ESLint
npx prisma migrate deploy    # Run pending migrations
npx prisma studio            # Open database GUI
```

## Project Structure

```
src/
  app/           # Next.js App Router pages and API routes
  components/    # React components organized by feature (landing/, dashboard/, admin/, coach/, modules/, courses/)
  lib/           # Business logic, DB queries, helpers (prisma.ts, courses.ts, cohorts.ts, modules.ts, email.ts)
  config/        # Course and instructor configuration
  types/         # Shared TypeScript types
  __tests__/     # Tests mirroring src/ structure
content/         # Course content as markdown files with front matter
prisma/          # Database schema and migrations
scripts/         # Seed, backfill, and sync utilities
docs/            # Documentation (Stripe setup, testing guide, etc.)
```

## Key Patterns

### Database (Prisma)
- Client singleton at `src/lib/prisma.ts` — always import from there
- Business logic queries live in `src/lib/` (e.g., `courses.ts`, `cohorts.ts`, `modules.ts`)
- Use `include` for related data to avoid N+1 queries

### API Routes
- Auth: `const { userId } = await auth()` from `@clerk/nextjs/server`
- Role check: fetch user from DB, check `user.role` (ADMIN, COACH, PARTICIPANT)
- Dynamic route params: `const { id } = await params` (Next.js 15 — params is a Promise)
- Return `NextResponse.json()` with appropriate status codes

### Components
- Server components by default; add `'use client'` only when interactivity is needed
- Organized by feature area under `src/components/`
- No component library — Tailwind + custom styles

### Content System
- Course content lives as markdown in `content/modules/`
- Front matter has metadata (title, slug, exercises, emailContent, etc.)
- `npm run sync-modules` syncs markdown to database
- Module access gated by `CohortModuleRelease` records

### Auth (Clerk)
- Middleware at `src/middleware.ts` protects all routes except public ones
- Public routes: `/`, `/sign-in`, `/sign-up`, `/enroll`, `/api/webhooks/stripe`, `/api/cron(.*)`
- User roles: ADMIN, COACH, PARTICIPANT

## Testing
- Framework: Vitest (not Jest)
- Tests in `src/__tests__/` mirroring `src/` structure
- Mock Prisma with `vi.hoisted()` + `vi.mock('@/lib/prisma', ...)`
- **New code must have tests.** Any new component, utility, or API route should be accompanied by tests in the same PR.
- **Run `npm run test:run` before every push to GitHub.** Do not push if tests are failing.
- **Never assert on Tailwind class strings.** Tests that check for specific classes (e.g. `pt-[22px]`, `bg-indigo-600`) break any time spacing or styling is tweaked, even when the component is structurally correct. Instead assert on DOM structure (child count, element presence), text content, ARIA roles, or `data-testid` attributes — things that reflect what the user actually sees.
