---
name: preflight
description: Run before starting any implementation work — verifies branch, repo, worktree, and open PRs.
---

# Pre-flight Check

Run this before making any edits. State each result explicitly and wait for confirmation before proceeding.

## Steps

1. **Branch** — `git branch --show-current`. State the branch name. If it's `main` and the task involves a code change, stop and ask whether to create a feature branch.

2. **Repo** — `git remote -v | head -2` + `basename $(git rev-parse --show-toplevel)`. State the repo name. Confirm it matches the intended target repo.

3. **Worktrees** — `git worktree list`. List any active worktrees. If multiple exist, confirm which one we're working in.

4. **Uncommitted changes** — `git status --short`. If there are staged or unstaged changes, list them and ask whether to commit, stash, or carry them forward.

5. **Open PRs from this branch** — `gh pr list --repo $(git remote get-url origin | sed 's/.*github.com\///' | sed 's/\.git$//') --head $(git branch --show-current) --json number,title,state 2>/dev/null`. If a PR already exists for this branch, surface it.

6. **Summary** — Print one line: `[branch: X | repo: Y | worktrees: N | status: clean/dirty]`

## Output format

```
Pre-flight:
  Branch: <name> [ok / ⚠️ main — create feature branch?]
  Repo: <name> [ok / ⚠️ unexpected]
  Worktrees: <list or "none">
  Status: <clean / dirty — N files>
  Open PR: <#N title / none>

Ready to proceed? [confirm or redirect]
```

Wait for explicit confirmation before making any edits.

## Living document

Update this skill when:
- The pre-PR checks change (a new lint / test / guard)
- CI starts catching something preflight should have
- The confirm / gate flow changes
