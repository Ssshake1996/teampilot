# Changelog

## 0.6.1 — 2026-11-05

- Guard nullable task details inside deferred component slots, including responsibility permissions, handover information, delivery evidence and review controls; missing details keep actions unavailable.
- Run an explicit forced Vue type-check in CI before unit tests and the production build, without weakening TypeScript null checks or adding non-null assertions.
- Align application and release metadata at `0.6.1`; no database schema or business workflow changes.

## 0.6.0 — 2026-11-04

- Add a team collaboration workspace for accountable owners, collaborators, handover acceptance, acceptance criteria, delivery evidence and designated review/return decisions.
- Persist blockers with handlers, next actions, deadlines, overdue escalation owners and resolution records; record schedule, effort and responsibility changes with before/after values and reasons.
- Plan explicit weekly capacity and per-person leaf-task hours, with visible over-allocation and protection against parent/child double counting.
- Add milestones, dependency cycle checks, immutable planning baselines, weekly commitments and retrospectives that create owned follow-up tasks.
- Replace personal fast/slow rankings with delivery evidence and items requiring support; retain report versions and historical commitments when tasks are later reopened.
- Add company/private project visibility, read-only observers, project leadership transfer and checks before removing, demoting or deactivating people who still hold unfinished responsibilities.
- Enforce project scope across legacy APIs, dashboards, personnel task aggregates, report caches/history/sending and realtime notifications.
- Add explicit, repeatable database migrations; existing business records remain intact and legacy tasks are marked for responsibility confirmation rather than assigned arbitrary owners.

## 0.5.0 — 2026-11-03

- Replace the settings Data Connectors tab with model provider configuration, using provider presets, protocol-specific authentication, custom headers, model discovery/manual selection and inference connection tests.
- Support OpenAI Chat Completions, OpenAI Responses and Anthropic Messages; preserve gateway URL prefixes.
- Encrypt provider credentials and keep saved secrets out of API responses. Preserve existing business data and delegated settings permissions.
- Persist the generated encryption key in the `provider_secrets` Compose volume, or configure `MODEL_PROVIDER_ENCRYPTION_KEY`; back up the key with the database when moving servers.
- Align frontend and backend version metadata at `0.5.0` and publish source and production Web assets with SHA-256 checksums.

## 0.4.0 — 2026-10-31

- Remove the native DSH plugin, its runtime/build dependencies, dedicated business-query and draft-approval endpoints, and plugin release checks.
- Keep project, task, personnel, manual progress, deterministic reports and task data Skill workflows available as an independent Web application.
- Preserve existing business records and legacy draft history during database upgrades; retired integrations are no longer exposed at runtime.
- Remove plugin instructions and UI links while keeping the published 0.3.0 release history below unchanged.
- Align frontend and backend version metadata at `0.4.0`; publish source and production Web assets without a plugin package.
- Exclude machine-local assistant settings from tracked source and release archives.

## 0.3.0 — 2026-10-31

### Frontend and interaction

- Open the selected task directly from task lists, dashboard activity and personnel details. Return links and account-scoped view state preserve navigation context.
- Sort the complete filtered task set before pagination, with validated fields, stable ordering and missing values last.
- Distinguish unavailable, loading, empty and stale data. Project, task, dashboard, personnel and settings views provide visible retry and update information.
- Prevent duplicate progress submission and preserve input on failure. Explain parent task progress and project completion-rate calculations.
- Prioritize project risks and recent progress for management roles; keep personal tasks first for members and compress empty task sections.
- Label team workload as estimated hours for all unfinished work, disclose fallback estimates, and avoid presenting it as weekly capacity utilization.
- Add personnel pagination and mobile cards, responsive tools and details, keyboard navigation, explicit project actions and date labels.

### Native DSH integration

- Ship the native TeamPilot plugin with DSH-owned conversations, models, navigation and runtime approvals. Compatibility remains DSH Web `0.2.0-rc.2`.
- Show readable before/after business fields, approved-but-not-written state, approval expiry and the next step back in the DSH conversation.
- Refresh drafts when opening the review tab and restore non-secret input/view state by account. Preserve project selection across pages.
- Keep backend authorization, revision, expiry and transaction checks, plus the separate DSH runtime approval. Approval does not itself write a business change.

### Packaging and upgrade

- Align application, backend API and plugin version metadata at `0.3.0`.
- Release source, production Web assets and the native plugin separately, with SHA-256 checksums.
- Include the consolidated Alembic migrations and existing DSH backend integration required by this release; retain business records during upgrades.
- Correct the production Nginx WebSocket route to match `/ws`.

### Compatibility

- Python 3.11; Node `^20.19.0 || >=22.12.0`; PostgreSQL 16 or SQLite.
- Back up the database and run `python -m alembic upgrade head` before production upgrades. See [deployment](docs/DEPLOYMENT.md) and [maintenance](docs/MAINTENANCE.md).
- GitHub release artifacts do not contain local configuration, credentials, databases, chat exports or private acceptance data.
