from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler

from admission_parser.stage2.pipeline_runner import run


def start_weekly(config_path: str = "configs/universities.yaml") -> None:
    scheduler = BlockingScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(run, "cron", day_of_week="mon,wed,fri", hour=10, minute=30, args=[config_path])
    scheduler.start()
