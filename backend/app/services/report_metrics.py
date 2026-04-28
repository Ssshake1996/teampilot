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


def _split_assignees(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace(",", "、").split("、") if item.strip()]


def progress_rankings(
    projects: list[dict],
    progress: list[dict],
    period_start: date,
    period_end: date,
    fast_default: str,
    slow_default: str,
) -> tuple[list[str], list[str]]:
    stats: dict[str, dict[str, float | int]] = {}

    for project in projects:
        for task in project.get("tasks") or []:
            progress_pct = float(task.get("progress_pct") or 0)
            status = str(task.get("status") or "")
            deadline = _parse_date(task.get("deadline"))
            is_overdue = bool(deadline and deadline < period_end and status != "done")
            for assignee in _split_assignees(task.get("assignee")):
                item = stats.setdefault(assignee, {
                    "task_count": 0,
                    "progress_sum": 0.0,
                    "overdue_count": 0,
                    "update_count": 0,
                })
                item["task_count"] = int(item["task_count"]) + 1
                item["progress_sum"] = float(item["progress_sum"]) + progress_pct
                if is_overdue:
                    item["overdue_count"] = int(item["overdue_count"]) + 1

    for item in progress:
        progress_date = _parse_date(item.get("created_at"))
        user = str(item.get("user") or "").strip()
        if not progress_date or not user or progress_date < period_start or progress_date > period_end:
            continue
        stat = stats.setdefault(user, {
            "task_count": 0,
            "progress_sum": 0.0,
            "overdue_count": 0,
            "update_count": 0,
        })
        stat["update_count"] = int(stat["update_count"]) + 1

    ranked: list[dict[str, Any]] = []
    for user, item in stats.items():
        task_count = int(item["task_count"])
        if task_count <= 0:
            continue
        avg_progress = round(float(item["progress_sum"]) / task_count)
        update_count = int(item["update_count"])
        overdue_count = int(item["overdue_count"])
        score = avg_progress + update_count * 5 - overdue_count * 12
        ranked.append({
            "user": user,
            "task_count": task_count,
            "avg_progress": avg_progress,
            "update_count": update_count,
            "overdue_count": overdue_count,
            "score": score,
        })

    if not ranked:
        return [fast_default], [slow_default]

    fast_rows = sorted(
        ranked,
        key=lambda item: (item["score"], item["avg_progress"], item["update_count"]),
        reverse=True,
    )[:3]
    slow_rows = sorted(
        ranked,
        key=lambda item: (item["score"], -item["overdue_count"], item["avg_progress"]),
    )[:3]

    def format_row(item: dict[str, Any]) -> str:
        bits = [
            f"{item['user']}：平均进度 {item['avg_progress']}%",
            f"负责 {item['task_count']} 项",
            f"本期更新 {item['update_count']} 条",
        ]
        if item["overdue_count"]:
            bits.append(f"逾期 {item['overdue_count']} 项")
        return "，".join(bits)

    return [format_row(item) for item in fast_rows], [format_row(item) for item in slow_rows]
