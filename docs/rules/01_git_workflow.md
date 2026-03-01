# Git Workflow Guide

## Branch Strategy (Git Flow)

This project follows a **Git Flow** branching model with three main branch types.

```
main ──────●────────────────●──────────
            \              /
develop ─────●──●──●──●──●───────────
              \       /
feature/xxx ───●──●──●　
```

### Branch Types

| Branch | Purpose | Branch from | Merge to |
|---|---|---|---|
| `main` | Production-ready code. Always deployable. | - | - |
| `develop` | Integration branch for the next release. | `main` | `main` |
| `feature/*` | New feature development. | `develop` | `develop` |
| `hotfix/*` | Urgent production fixes. | `main` | `main` + `develop` |
| `release/*` | Release preparation (version bump, final fixes). | `develop` | `main` + `develop` |

## Commit Message Convention (Conventional Commits)

### Format

```
<type>(<scope>): <short description>

<body (optional)>
```

### Types

| Type | Description |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |.  
| `docs` | Documentation only | 
| `refactor` | Code refactoring (no functional change) | 
| `test` | Adding or updating tests |
| `chore` | Build tools, CI/CD, dependencies |

### Examples

```
feat(auth): add OAuth2 login support
fix(api): resolve encoding issue in response
docs: add setup instructions to README
refactor(categorizer): simplify scoring logic
```

## Rules

### Must Do

1. **One commit = one logical change** — Keep commits small and focused.
2. **Use Pull Requests (PRs)** — Never push directly to `main` or `develop`.
3. **Require at least one review** before merging a PR.
4. **Pull the latest changes** before starting new work.
5. **Maintain `.gitignore`** — Do not track generated files, secrets, or IDE configs.

### Must NOT Do

1. **Never `force push` to shared branches** (`main`, `develop`) — This destroys others' work.
2. **Never commit secrets** — `.env`, API keys, passwords, tokens, etc.
3. **Never commit large binaries** — Use Git LFS if needed.
4. **Never commit directly to `main`** — Always go through PRs.

## Daily Workflow

```bash
# 1. Sync with the latest develop
git checkout develop
git pull origin develop

# 2. Create a feature branch
git checkout -b feature/<feature-name>

# 3. Work and commit
git add <files>
git commit -m "feat(<scope>): add new feature"

# 4. Push to remote
git push -u origin feature/<feature-name>

# 5. Create a Pull Request (develop <- feature/*)
# 6. After review, merge into develop

# 7. When ready for release, merge develop into main
```

## Hotfix Workflow

```bash
# 1. Branch from main
git checkout main
git pull origin main
git checkout -b hotfix/<issue-description>

# 2. Fix and commit
git add <files>
git commit -m "fix(<scope>): resolve critical issue"

# 3. Create PR to main AND merge back into develop
git push -u origin hotfix/<issue-description>
```

## Branch Naming Convention

```
feature/<short-description>    e.g. feature/stt-support
hotfix/<short-description>     e.g. hotfix/fix-api-timeout
release/<version>              e.g. release/1.2.0
```

- Use lowercase with hyphens (`-`) as separators.
- Keep names short but descriptive.
