# TeamPilot Native DSH Plugin

## Scope

Targets **DSH 0.2.0-rc.2**, the official npm `latest` channel checked on
2026-10-05, and Node **22.12+** (tested with Node 24).
This is a native Cordis Host + React Client plugin, not an iframe, a model proxy,
or a second Agent runtime. DSH owns models, credentials, conversations, tool
dispatch, cancellation and runtime approval. TeamPilot owns JWT authentication,
RBAC, task state, weights, transactions and business audit.

The former TeamPilot LLM modules, `/api/v1/ai` routes and Vue AI controls are
removed. There is no fallback to the old implementation. Manual Web management,
rule-based daily/weekly reports, SMTP and deterministic data collection remain.

## Local Development

Start the TeamPilot backend on `127.0.0.1:8000`. Then from the repository:

```bash
cd plugins
npm ci
npm run build
npm test
npm run dev
```

The launcher serves DSH on `127.0.0.1:5180`, with a separate home at
`plugins/.dsh-home`. It does not overwrite a global DSH installation, copy old
model keys or open browser windows automatically. Use the local authentication
link printed by DSH; do not share the link or commit this home directory.
Configure the model in DSH's own model settings.

Open TeamPilot from the shared plugin navigation. It uses a native right-sidebar
tab and the same DSH controls as the other plugins. Log in with your own
TeamPilot account, choose one project or all accessible projects, and enter a
query such as "summarize current project progress and identify overdue tasks".
Without the optional shared navigation plugin, TeamPilot keeps its native footer
action. The built-in plugin manager alone does not suppress that business entry.
Analysis results appear in a new native DSH conversation and support follow-up
questions; requesting a report alone never authorizes a business draft. The plugin selects
the TeamPilot Agent preset before submitting the prompt through the public
Session Controller. Its allowlist excludes shell, direct database access and
generic file/network tools. Native clarification remains available.

## Read-only Queries

The Agent can inspect the authenticated account, paginated projects and tasks,
raw progress notes with author and timestamps, project members, personnel,
skills and dated report snapshots. Cross-project task/progress queries support
project, task, assignee/author, status, keyword and date-range filters. Raw
progress requires `progress.view`; every request rechecks current account
permissions. Date ranges are UTC instants with an inclusive start and exclusive
end. Pagination uses 50-item pages; the Agent must follow `has_more` and disclose
incomplete coverage. Archived/deleted projects are excluded by default.

## Draft Workflow

1. Agent reads permitted, paginated business context and proposes a strict draft.
2. Open **草稿审阅** (it refreshes on entry), select the draft and review the
   labelled before/after business fields. Changed fields are highlighted, assignees
   use their review-time display names, and the exact JSON remains expandable.
   Check the exact-content confirmation and approve.
3. The panel now says **已批准，尚未写入** and shows the separate approval expiry.
   Copy its exact-draft submission request into the native conversation, or open
   the last TeamPilot conversation. DSH displays a separate
   runtime approval; rejection or an unavailable approval channel prevents writes.
4. TeamPilot rechecks the author, RBAC, project revision and expiry, atomically
   commits through its existing services, and returns the result. The Web UI
   receives its normal post-commit WebSocket update.

Supported draft kinds:

- `project_plan`: new project with bounded recursive task tree.
- `task_create`: additional tasks/subtasks in an existing project.
- `progress`: up to 100 unique task progress updates within one project.
- `task_update`: only specified title/goal/description/priority/assignees/hours/
  dates/weight fields change. Completion status, signoff and deletion are forbidden.

Plan limits: 200 tasks, 8 levels, 100 children per node. New siblings use existing
equal-weight redistribution. Adding children reopens completed ancestors without
removing their audit history. Weight tolerance remains `0.01`.

Drafts expire after one hour. Approval expires after five minutes. Changed project
revisions require a new draft; the plugin never silently overwrites newer work.
Backend retries with the same confirmation token are idempotent. Cancellation
before commit prevents writing; cancellation or network loss after dispatch is
not a promise to undo a transaction. Read the draft state before retrying.

One DSH Host binds **one business account**. Tokens and confirmation secrets live
only in Host memory, are not returned to tools, and disappear on logout/unload/
restart. After restart reapprove a still-valid draft. Use a separate DSH home per
person. This is not a company-wide multi-tenant DSH gateway, and trusted Host
extensions or local administrators are not sandboxed by this plugin.

The native panel displays both the one-hour draft expiry and five-minute approval
expiry. It also detects when this Host no longer holds an approved draft's secret,
so a restart cannot misleadingly look ready to commit. These status fields contain
no confirmation token. Reapprove the unchanged draft if the short approval expires.

Unsubmitted query text, selected project and tab/review position are saved in this
browser per TeamPilot origin/account. Passwords and approval secrets never persist.
Successful admission clears the saved query and records its native conversation.
Project-name search filters the current 50-item project page; the selected project
stays visible when paging or filtering, and the exact selected scope is repeated
below the selector. Explicit refresh remains available, with separate list errors
and last-read timestamps rather than interpreting a failed request as an empty list.

## Packaging / Existing DSH

```bash
cd plugins
npm run build
npm pack -w dsh-teampilot
```

Install the resulting `dsh-teampilot-0.3.0.tgz` into the compatible DSH profile
using its native plugin manager. Do not install it into the older 0.1.x runtime.
The package declares a native `dsh.bundle`; installation activates it without
manually copying development files or editing another plugin:

```bash
dsh plugin --profile web add /absolute/path/to/dsh-teampilot-0.3.0.tgz
```

Restart the Web instance after installation. The included profile entry uses
the official patch format:

```yaml
- insert:
    - id: teampilot
      name: dsh-teampilot
      config:
        baseUrl: http://127.0.0.1:8000
```

Only loopback HTTP is allowed; remote TeamPilot origins must use HTTPS. Redirects
are rejected, requests have a 30-second timeout, and responses have a 2 MiB cap.
Generated Typert Host/Client contracts are built from the pinned official
generator. Its npm workspace-reflection limitation is handled by staging the
exact installed declarations during build, not by changing upstream source.

## Verification Boundaries

`npm test` exercises the actual DSH ToolRuntime with a mock business HTTP service,
native client registration/disposal, and conversation submission against mocked
public Session Controller faces. It does not prove model inference or browser
interaction. Review tests also cover changed-field presentation, names, scoped
input persistence without credentials, exact project selection across pages,
and the difference between draft/approval expiry and lost Host credentials.
Backend tests cover RBAC, ownership, conflicts, expiry, rollback,
idempotency and task-tree rules. `plugins/scripts/check-web.mjs` checks the real
local DSH browser panel at desktop/mobile widths. Frontend regression uses
`frontend/scripts/check-ui.mjs`.

Real model inference requires DSH credentials and is a separate acceptance test.
Electron Desktop and PostgreSQL concurrency are not implied by passing the local
Web/SQLite tests. The existing GitHub workflow includes backend/frontend/plugin
builds and tests; remote CI execution must be checked separately.
