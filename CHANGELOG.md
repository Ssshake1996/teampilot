# Changelog

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
