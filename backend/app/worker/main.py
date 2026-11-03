"""Scheduled worker. Run: python -m app.worker.main"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from app.db import SessionLocal
from app.worker import health_job, notifier, satellite_job, status_job

log = logging.getLogger("worker")


def _job(fn):
    def wrapper():
        with SessionLocal() as db:
            try:
                fn(db)
            except Exception:
                db.rollback()
                log.exception("job %s failed", fn.__module__)

    wrapper.__name__ = fn.__module__
    return wrapper


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sched = BlockingScheduler(timezone="Asia/Jakarta")
    # A minute after each 10-min bucket closes, so the aggregate includes it.
    sched.add_job(_job(health_job.run), "cron", minute="1,11,21,31,41,51", max_instances=1)
    sched.add_job(_job(status_job.run), "cron", minute="2,12,22,32,42,52", max_instances=1)
    sched.add_job(_job(notifier.send_due), "interval", seconds=30, max_instances=1)
    sched.add_job(_job(satellite_job.run), "cron", hour=6, minute=30, max_instances=1)
    log.info("worker started")
    sched.start()


if __name__ == "__main__":
    main()
