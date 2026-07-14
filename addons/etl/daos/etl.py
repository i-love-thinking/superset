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
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import or_

from superset.extensions import db

from addons.etl.models import EtlJob, EtlJobLog, EtlJobSource, EtlState

logger = logging.getLogger(__name__)


class EtlJobDAO:
    """Data access layer for EtlJob."""

    @staticmethod
    def find_by_id(job_id: int) -> Optional[EtlJob]:
        return db.session.query(EtlJob).filter_by(id=job_id).one_or_none()

    @staticmethod
    def find_all() -> list[EtlJob]:
        return db.session.query(EtlJob).all()

    @staticmethod
    def find_active_cron() -> list[EtlJob]:
        """Return all active jobs that use a cron schedule."""
        from addons.etl.models import EtlScheduleType

        return (
            db.session.query(EtlJob)
            .filter(
                EtlJob.active.is_(True),
                EtlJob.schedule_type == EtlScheduleType.CRON,
                EtlJob.crontab.isnot(None),
            )
            .all()
        )

    @staticmethod
    def find_due_onetime(now: datetime) -> list[EtlJob]:
        """Return active one-time jobs whose run_at is in the past."""
        from addons.etl.models import EtlScheduleType

        return (
            db.session.query(EtlJob)
            .filter(
                EtlJob.active.is_(True),
                EtlJob.schedule_type == EtlScheduleType.ONETIME,
                EtlJob.run_at.isnot(None),
                EtlJob.run_at <= now,
            )
            .all()
        )

    @staticmethod
    def create(properties: dict[str, Any]) -> EtlJob:
        sources_data: list[dict[str, Any]] = properties.pop("sources", [])
        job = EtlJob(**properties)
        db.session.add(job)
        db.session.flush()  # get job.id before inserting sources

        for idx, src_data in enumerate(sources_data):
            src_data.setdefault("order", idx)
            source = EtlJobSource(etl_job_id=job.id, **src_data)
            db.session.add(source)

        db.session.commit()
        return job

    @staticmethod
    def update(job: EtlJob, properties: dict[str, Any]) -> EtlJob:
        sources_data: list[dict[str, Any]] | None = properties.pop("sources", None)

        for key, value in properties.items():
            setattr(job, key, value)

        if sources_data is not None:
            # Replace all existing sources
            db.session.query(EtlJobSource).filter_by(etl_job_id=job.id).delete()
            for idx, src_data in enumerate(sources_data):
                src_data.setdefault("order", idx)
                source = EtlJobSource(etl_job_id=job.id, **src_data)
                db.session.add(source)

        db.session.commit()
        return job

    @staticmethod
    def delete(job: EtlJob) -> None:
        db.session.delete(job)
        db.session.commit()

    @staticmethod
    def update_last_run(job_id: int, state: str) -> None:
        db.session.query(EtlJob).filter_by(id=job_id).update(
            {"last_run_dttm": datetime.utcnow(), "last_run_state": state}
        )
        db.session.commit()

    @staticmethod
    def deactivate(job_id: int) -> None:
        """Deactivate a one-time job after it has been executed."""
        db.session.query(EtlJob).filter_by(id=job_id).update({"active": False})
        db.session.commit()


class EtlJobLogDAO:
    """Data access layer for EtlJobLog."""

    @staticmethod
    def create_log(
        job_id: int,
        scheduled_dttm: Optional[datetime] = None,
        celery_task_id: Optional[str] = None,
    ) -> EtlJobLog:
        log = EtlJobLog(
            etl_job_id=job_id,
            scheduled_dttm=scheduled_dttm,
            start_dttm=datetime.utcnow(),
            state=EtlState.WORKING,
            celery_task_id=celery_task_id,
        )
        db.session.add(log)
        db.session.commit()
        return log

    @staticmethod
    def update_log(
        log: EtlJobLog,
        state: str,
        error_message: Optional[str] = None,
        rows_imported: Optional[int] = None,
    ) -> EtlJobLog:
        log.state = state
        log.end_dttm = datetime.utcnow()
        if error_message is not None:
            log.error_message = error_message
        if rows_imported is not None:
            log.rows_imported = rows_imported
        db.session.commit()
        return log

    @staticmethod
    def find_by_job(
        job_id: int,
        page: int = 0,
        page_size: int = 50,
    ) -> tuple[list[EtlJobLog], int]:
        query = db.session.query(EtlJobLog).filter_by(etl_job_id=job_id)
        total = query.count()
        logs = (
            query.order_by(EtlJobLog.start_dttm.desc())
            .offset(page * page_size)
            .limit(page_size)
            .all()
        )
        return logs, total

    @staticmethod
    def prune_old_logs(job_id: int, retention_days: int) -> int:
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        deleted = (
            db.session.query(EtlJobLog)
            .filter(
                EtlJobLog.etl_job_id == job_id,
                EtlJobLog.start_dttm < cutoff,
            )
            .delete(synchronize_session="fetch")
        )
        db.session.commit()
        return deleted

    @staticmethod
    def prune_all_old_logs() -> int:
        """Prune logs across all jobs respecting each job's log_retention setting."""
        total_deleted = 0
        jobs = db.session.query(EtlJob).all()
        for job in jobs:
            total_deleted += EtlJobLogDAO.prune_old_logs(job.id, job.log_retention)
        return total_deleted
