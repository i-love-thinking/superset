# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""
Celery tasks for the ETL addon.

Task names
----------
etl.scheduler  – triggered every minute by Celery Beat; dispatches etl.execute
etl.execute    – downloads files and imports to the target database
etl.prune_log  – cleans up old EtlJobLog rows (runs daily)

Configuration
-------------
Add the following to your CeleryConfig in superset_config.py:

    class CeleryConfig:
        imports = (
            "superset.sql_lab",
            "superset.tasks.cache",
            "superset.tasks.slack",
            "addons.etl.tasks.scheduler",   # <-- add this
        )
        beat_schedule = {
            ...
            "etl.scheduler": {
                "task": "etl.scheduler",
                "schedule": crontab(minute="*", hour="*"),
            },
            "etl.prune_log": {
                "task": "etl.prune_log",
                "schedule": crontab(minute=0, hour=1),
            },
        }
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from celery import Task

from superset import is_feature_enabled
from superset.extensions import celery_app

logger = logging.getLogger(__name__)

_FEATURE_FLAG = "ENABLE_ETL_JOBS"


# ---------------------------------------------------------------------------
# Scheduler  (runs every minute via Celery Beat)
# ---------------------------------------------------------------------------


@celery_app.task(
    name="etl.scheduler",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
)
def scheduler(self: Task) -> None:  # pylint: disable=unused-argument
    """
    Scan active EtlJob records and dispatch etl.execute tasks for those
    that are due to run according to their cron schedule, or for one-time
    jobs whose run_at has passed.
    """
    if not is_feature_enabled(_FEATURE_FLAG):
        return

    from superset.tasks.cron_util import cron_schedule_window

    from addons.etl.daos.etl import EtlJobDAO
    from addons.etl.models import EtlScheduleType

    # ── Cron-based jobs ───────────────────────────────────────────────
    triggered_at = datetime.now(tz=timezone.utc)

    for job in EtlJobDAO.find_active_cron():
        for schedule in cron_schedule_window(
            triggered_at, job.crontab, job.timezone  # type: ignore[arg-type]
        ):
            logger.info(
                "Scheduling ETL job %s (%s) eta: %s", job.id, job.name, schedule
            )
            execute.apply_async(
                kwargs={"job_id": job.id, "scheduled_dttm": schedule.isoformat()},
                eta=schedule,
                time_limit=job.working_timeout + 60,
                soft_time_limit=job.working_timeout,
            )

    # ── One-time jobs ─────────────────────────────────────────────────
    now_naive = datetime.utcnow()
    for job in EtlJobDAO.find_due_onetime(now_naive):
        logger.info(
            "Scheduling one-time ETL job %s (%s)", job.id, job.name
        )
        execute.apply_async(
            kwargs={"job_id": job.id},
            time_limit=job.working_timeout + 60,
            soft_time_limit=job.working_timeout,
        )


# ---------------------------------------------------------------------------
# Executor  (performs the actual download + import)
# ---------------------------------------------------------------------------


@celery_app.task(
    name="etl.execute",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 1, "countdown": 30},
)
def execute(  # pylint: disable=unused-argument
    self: Task,
    job_id: int,
    scheduled_dttm: Optional[str] = None,
) -> None:
    """
    Download remote file(s) and import them into the configured database.

    Parameters
    ----------
    job_id:
        Primary key of the EtlJob to execute.
    scheduled_dttm:
        ISO-8601 string representing the scheduler's intended fire time.
        None for manually-triggered executions.
    """
    if not is_feature_enabled(_FEATURE_FLAG):
        return

    from addons.etl.commands.execute import ExecuteEtlJobCommand

    sched_dt: Optional[datetime] = None
    if scheduled_dttm:
        try:
            sched_dt = datetime.fromisoformat(scheduled_dttm)
        except ValueError:
            logger.warning("Could not parse scheduled_dttm: %s", scheduled_dttm)

    celery_task_id: Optional[str] = execute.request.id

    ExecuteEtlJobCommand(
        job_id=job_id,
        scheduled_dttm=sched_dt,
        celery_task_id=celery_task_id,
    ).run()


# ---------------------------------------------------------------------------
# Log pruner  (runs daily)
# ---------------------------------------------------------------------------


@celery_app.task(name="etl.prune_log")
def prune_log() -> None:
    """Remove EtlJobLog rows older than each job's log_retention setting."""
    if not is_feature_enabled(_FEATURE_FLAG):
        return

    from addons.etl.daos.etl import EtlJobLogDAO

    deleted = EtlJobLogDAO.prune_all_old_logs()
    logger.info("ETL prune_log: deleted %d old log rows", deleted)
