# Development Guide

This document describes the cleaned GitHub repository structure and the boundaries that should stay stable while the project evolves.

## Public Repository Contents

Keep these paths in the repository:

```text
.github/workflows/ci.yml
.gitignore
README.md
apps/local-web/backend
apps/local-web/frontend
apps/local-web/desktop
apps/local-web/plugins/rag-core
docs/onboarding-guide.md
docs/development.md
docs/integration
docs/release
```

Do not commit runtime data, generated assets, local databases, benchmark outputs, release staging folders, test caches, or dependency directories.

## Engineering Shape

The repository uses a compact application workspace:

- `apps/local-web/backend` owns business state, persistence, migrations, and API contracts.
- `apps/local-web/frontend` owns user interaction, views, localization, and client-side API wrappers.
- `apps/local-web/desktop` owns Tauri runtime startup, data-directory behavior, and Windows release packaging.
- `apps/local-web/plugins/rag-core` owns local AI capabilities behind plugin task contracts.

The code intentionally keeps app state in the backend. The plugin may generate cards, score explanations, or suggest scheduling changes, but it must not mutate the SQLite database directly.

## Naming

The public project name is `AI Memory Card`.

Package and runtime names have been normalized for the public repository:

- Backend package/environment: `ai-memory-card-backend`
- Frontend package: `ai-memory-card-frontend`
- Desktop package: `ai-memory-card-desktop`
- Default SQLite file: `ai_memory_card.db`
- Windows app data root: `AIMemoryCard`

## Backend Boundaries

Core backend services:

- `CardService`
- `RAGImportService`
- `EvaluationService`
- `ReviewService`
- `ActivityService`
- `StudySettingsService`
- `AIPluginHostService`

Review scheduling is split into two concerns:

- `ReviewService` manages review session validation, queue state, persistence, undo, and response shaping.
- `AISchedulerDecisionService` owns optional AI/RL interval adjustment and fallback behavior.

This split keeps plugin errors away from review-session integrity.

## Frontend Boundaries

Frontend conventions:

- `pages` compose full routes.
- `features` implement domain-specific panels and flows.
- `api` wraps HTTP/Tauri calls.
- `components/ui` contains reusable primitives.
- `i18n/locales` stores visible copy.

When a backend schema changes, update `frontend/src/api/types.ts` and affected tests in the same change.

## Plugin Boundaries

`rag-core` provides task-based capabilities:

- `rag.generate_cards`
- `evaluation.score_explanation`
- `scheduler.plan_review`

The backend validates plugin output before persistence. Scheduler plugin output is especially constrained: it can adjust interval recommendations, not today's queue mechanics or grade semantics.

## Verification Checklist

Run the smallest relevant subset while developing, then run the broader suite before publishing:

```powershell
pytest apps/local-web/backend/tests -q
```

```powershell
cd apps/local-web/plugins/rag-core
pytest tests runtime/tests -q
```

```powershell
cd apps/local-web/frontend
npm.cmd test
npm.cmd run build
```

```powershell
cd apps/local-web/desktop
npm.cmd run test:doctor
npm.cmd run test:prepare-release
npm.cmd run test:release-local
npm.cmd run test:portable
npm.cmd run test:run-tauri
```

## Cleanup Policy

Safe to delete locally:

- `node_modules`
- `dist`
- `target`
- `.release-staging`
- `.release-output`
- `.pytest_cache`
- `.pytest-temp`
- `__pycache__`
- local `data`, `cache`, `backups`, `plugin-state`, `plugins`, `temp`, and `logs`

Keep out of Git:

- `.db`, `.sqlite`, `.sqlite3`
- release installers/zips
- research experiment outputs
- thesis or personal draft material
- local API keys or `.env` files
