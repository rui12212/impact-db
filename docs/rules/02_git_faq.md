# Git FAQ — Common Questions & Answers

A summary of common Git questions and answers for this project.

---

## Q1. What is the general Git branching strategy for this project?

We follow **Git Flow** with three main branch types:

| Branch | Purpose | Branch from | Merge to |
|---|---|---|---|
| `main` | Production-ready code. Always deployable. | - | - |
| `develop` | Integration branch for the next release. | `main` | `main` (via PR) |
| `feature/*` | New feature development. | `develop` | `develop` (via PR) |
| `hotfix/*` | Urgent production fixes. | `main` | `main` + `develop` |

```
main ──────●────────────────●──────────
            \              /
develop ─────●──●──●──●──●───────────
              \       /
feature/xxx ───●──●──●
```

See [01_git_workflow.md](01_git_workflow.md) for the full guide.

---

## Q2. How do I decide which branches to delete?

Use the following criteria:

| Criteria | Question to ask |
|---|---|
| **Merged?** | Is it already merged into `main`? → Safe to delete |
| **Superseded?** | Was its work carried over to a later branch? → Delete candidate |
| **Still needed?** | Is there any unmerged, valuable work left? → Keep or review |
| **Last updated** | Has it been inactive for a long time? → Likely abandoned |

**Commands to check:**

```bash
# Branches already merged into main → safe to delete
git branch --merged main

# Branches NOT yet merged → review before deleting
git branch --no-merged main

# Check how far ahead/behind a branch is from main
git rev-list --left-right --count main...<branch-name>
```

---

## Q3. How do I merge a feature branch into main?

Always use a **Pull Request (PR)** — never push directly to `main`.

```bash
# 1. Commit any remaining changes
git add <files>
git commit -m "feat: ..."

# 2. Push the branch to remote
git push origin feature/<name>

# 3. Create a PR on GitHub (feature/* → main)
gh pr create --base main --head feature/<name> --title "..." --body "..."

# 4. After review and approval, merge on GitHub
```

---

## Q4. How do I recreate the develop branch from main?

After merging everything into `main`, recreate `develop` from the latest `main`:

```bash
# 1. Switch to main and pull latest
git checkout main
git pull origin main

# 2. Delete old develop (local and remote)
git branch -D develop
git push origin --delete develop

# 3. Recreate develop from main
git checkout -b develop main

# 4. Push to remote
git push origin develop
```

---

## Q5. How do I delete merged branches (local + remote)?

```bash
# Delete a single branch
git branch -d feature/<name>                  # local
git push origin --delete feature/<name>       # remote

# Delete multiple branches at once
for branch in feature/foo feature/bar; do
  git branch -d "$branch"
  git push origin --delete "$branch"
done
```

> **Note:** Use `git branch --merged main` first to confirm they are safe to delete.

---

## Q6. How does a new collaborator check branches after cloning?

```bash
# 1. Clone the repository
git clone https://github.com/rui12212/impact-db.git
cd impact-db

# 2. Fetch all remote branch info
git fetch --all

# 3. List all branches (local + remote)
git branch -a
```

| Command | Shows |
|---|---|
| `git branch` | Local branches only |
| `git branch -r` | Remote branches only |
| `git branch -a` | Local + remote branches |

---

## Q7. Does a new collaborator need to create the develop branch on remote?

**No.** The `develop` branch already exists on the remote (`origin/develop`).

The collaborator only needs to create a **local** tracking branch that links to it:

```bash
git checkout develop
# Git automatically creates a local branch tracking origin/develop
```

**Before:**
```
Remote : origin/main, origin/develop  ✓ already exists
Local  : main only                    (created automatically by clone)
```

**After `git checkout develop`:**
```
Remote : origin/main, origin/develop
Local  : main, develop                ✓ now linked to origin/develop
```

From this point, `git pull` and `git push` will automatically sync with `origin/develop`.

---

## Q8. A collaborator can still see deleted branches with `git branch -r`. Why?

`git branch -r` does **not** query the remote directly — it shows **locally cached** remote branch info. If the collaborator hasn't fetched since the branches were deleted, the stale cache remains.

**Fix: run the following on the collaborator's terminal:**

```bash
git fetch --prune
```

Or separately:

```bash
git remote prune origin
```

After this, `git branch -r` will show only `origin/main` and `origin/develop`.

**Why doesn't it update automatically?**

```
Person who deleted  → git push --delete  (remote is updated immediately)
Collaborator        → must run git fetch to update their local cache
```

**Recommended: enable auto-prune globally**

```bash
git config --global fetch.prune true
```

With this setting, every `git fetch` (and `git pull`) will automatically remove stale remote-tracking branches.
