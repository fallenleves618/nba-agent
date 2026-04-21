from __future__ import annotations

from nba_agent.app import run_pipeline


def daily_job() -> None:
    run_pipeline(demo=False)


if __name__ == "__main__":
    daily_job()
