"""Evidence lists, retained under legacy API names without personal scoring."""
from datetime import date, datetime
from typing import Any


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def progress_rankings(projects: list[dict], progress: list[dict], period_start: date,
                      period_end: date, fast_default: str, slow_default: str) -> tuple[list[str], list[str]]:
    """Return deliveries and support items; repeated submissions do not affect them."""
    delivered, support, seen = [], [], set()
    for project in projects:
        for task in project.get("tasks") or []:
            identity = task.get("id") or (project.get("name"), task.get("title"))
            if identity in seen:
                continue
            seen.add(identity)
            line = f"{project.get('name', '')} / {task.get('title', '')}"
            signed = _parse_date(task.get("signed_off_at"))
            done = task.get("status") == "done"
            if done and signed and period_start <= signed <= period_end:
                delivered.append(f"{line}：{signed.isoformat()} 已验收交付")
            if done:
                continue
            reasons = []
            due = _parse_date(task.get("deadline"))
            if due and due < period_end:
                reasons.append(f"已逾期（原截止 {due.isoformat()}）")
            if float(task.get("progress_pct") or 0) >= 100:
                reasons.append("已达 100%，等待验收")
            if not str(task.get("assignee") or "").strip() or task.get("assignee") in {"未分配", "unassigned"}:
                reasons.append("尚未明确执行负责人")
            if reasons:
                support.append(f"{line}：{'；'.join(reasons)}")
    return delivered[:20] or ["本期暂无已验收交付成果。"], support[:20] or ["当前暂无明确的待支持事项。"]
