import asyncio

from sqlalchemy import inspect, text

from app.database import engine


def _has_goal_column(sync_conn) -> bool:
    return "goal" in {column["name"] for column in inspect(sync_conn).get_columns("projects")}


async def main() -> None:
    async with engine.begin() as conn:
        has_goal = await conn.run_sync(_has_goal_column)
        if not has_goal:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN goal TEXT"))
            print("[OK] Added projects.goal column")
        else:
            print("[OK] projects.goal column already exists")

        await conn.execute(
            text(
                "UPDATE projects "
                "SET goal = description "
                "WHERE (goal IS NULL OR TRIM(goal) = '') AND description IS NOT NULL"
            )
        )
        print("[OK] Backfilled empty project goals from description")


if __name__ == "__main__":
    asyncio.run(main())
