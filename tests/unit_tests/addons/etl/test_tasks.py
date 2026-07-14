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
Unit tests for the ETL Celery tasks in addons/etl/tasks/scheduler.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# etl.scheduler
# ---------------------------------------------------------------------------


@patch("addons.etl.tasks.scheduler.is_feature_enabled", return_value=False)
def test_scheduler_does_nothing_when_flag_disabled(
    mock_flag: MagicMock,
) -> None:
    from addons.etl.tasks.scheduler import scheduler

    with patch(
        "addons.etl.tasks.scheduler.EtlJobDAO"
    ) as mock_dao:
        scheduler()
        mock_dao.find_active_cron.assert_not_called()
        mock_dao.find_due_onetime.assert_not_called()


@patch("addons.etl.tasks.scheduler.is_feature_enabled", return_value=True)
@patch("addons.etl.tasks.scheduler.cron_schedule_window")
@patch("addons.etl.tasks.scheduler.EtlJobDAO")
@patch("addons.etl.tasks.scheduler.execute")
def test_scheduler_dispatches_cron_jobs(
    mock_execute: MagicMock,
    mock_dao: MagicMock,
    mock_cron_window: MagicMock,
    mock_flag: MagicMock,
) -> None:
    from addons.etl.models import EtlJob, EtlScheduleType

    job = MagicMock(spec=EtlJob)
    job.id = 1
    job.name = "cron_job"
    job.crontab = "0 * * * *"
    job.timezone = "UTC"
    job.working_timeout = 3600

    mock_dao.find_active_cron.return_value = [job]
    mock_dao.find_due_onetime.return_value = []
    mock_cron_window.return_value = [datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)]
    mock_execute.apply_async = MagicMock()

    from addons.etl.tasks.scheduler import scheduler

    scheduler()

    mock_execute.apply_async.assert_called_once()
    call_kwargs = mock_execute.apply_async.call_args[1]
    assert call_kwargs["kwargs"]["job_id"] == 1


@patch("addons.etl.tasks.scheduler.is_feature_enabled", return_value=True)
@patch("addons.etl.tasks.scheduler.EtlJobDAO")
@patch("addons.etl.tasks.scheduler.execute")
def test_scheduler_dispatches_onetime_jobs(
    mock_execute: MagicMock,
    mock_dao: MagicMock,
    mock_flag: MagicMock,
) -> None:
    from addons.etl.models import EtlJob, EtlScheduleType

    job = MagicMock(spec=EtlJob)
    job.id = 2
    job.name = "onetime_job"
    job.working_timeout = 1800

    mock_dao.find_active_cron.return_value = []
    mock_dao.find_due_onetime.return_value = [job]
    mock_execute.apply_async = MagicMock()

    from addons.etl.tasks.scheduler import scheduler

    scheduler()

    mock_execute.apply_async.assert_called_once()
    assert mock_execute.apply_async.call_args[1]["kwargs"]["job_id"] == 2


@patch("addons.etl.tasks.scheduler.is_feature_enabled", return_value=True)
@patch("addons.etl.tasks.scheduler.EtlJobDAO")
@patch("addons.etl.tasks.scheduler.execute")
@patch("addons.etl.tasks.scheduler.cron_schedule_window", return_value=[])
def test_scheduler_does_not_dispatch_when_no_schedules_match(
    mock_cron_window: MagicMock,
    mock_execute: MagicMock,
    mock_dao: MagicMock,
    mock_flag: MagicMock,
) -> None:
    mock_dao.find_active_cron.return_value = []
    mock_dao.find_due_onetime.return_value = []
    mock_execute.apply_async = MagicMock()

    from addons.etl.tasks.scheduler import scheduler

    scheduler()

    mock_execute.apply_async.assert_not_called()


# ---------------------------------------------------------------------------
# etl.execute
# ---------------------------------------------------------------------------


@patch("addons.etl.tasks.scheduler.is_feature_enabled", return_value=False)
def test_execute_task_does_nothing_when_flag_disabled(
    mock_flag: MagicMock,
) -> None:
    with patch(
        "addons.etl.tasks.scheduler.ExecuteEtlJobCommand"
    ) as mock_cmd:
        from addons.etl.tasks.scheduler import execute

        execute(job_id=1)
        mock_cmd.assert_not_called()


@patch("addons.etl.tasks.scheduler.is_feature_enabled", return_value=True)
@patch("addons.etl.tasks.scheduler.ExecuteEtlJobCommand")
def test_execute_task_runs_command(
    mock_cmd_cls: MagicMock,
    mock_flag: MagicMock,
) -> None:
    mock_cmd = MagicMock()
    mock_cmd_cls.return_value = mock_cmd

    from addons.etl.tasks.scheduler import execute

    execute(job_id=42, scheduled_dttm="2026-07-15T12:00:00")

    mock_cmd_cls.assert_called_once_with(
        job_id=42,
        scheduled_dttm=datetime(2026, 7, 15, 12, 0, 0),
        celery_task_id=None,  # request.id not available in unit test
    )
    mock_cmd.run.assert_called_once()


@patch("addons.etl.tasks.scheduler.is_feature_enabled", return_value=True)
@patch("addons.etl.tasks.scheduler.ExecuteEtlJobCommand")
def test_execute_task_handles_invalid_scheduled_dttm(
    mock_cmd_cls: MagicMock,
    mock_flag: MagicMock,
) -> None:
    mock_cmd = MagicMock()
    mock_cmd_cls.return_value = mock_cmd

    from addons.etl.tasks.scheduler import execute

    # Should not raise; bad datetime is logged and treated as None
    execute(job_id=1, scheduled_dttm="not-a-datetime")

    mock_cmd_cls.assert_called_once_with(
        job_id=1,
        scheduled_dttm=None,
        celery_task_id=None,
    )


# ---------------------------------------------------------------------------
# etl.prune_log
# ---------------------------------------------------------------------------


@patch("addons.etl.tasks.scheduler.is_feature_enabled", return_value=False)
def test_prune_log_does_nothing_when_flag_disabled(
    mock_flag: MagicMock,
) -> None:
    with patch(
        "addons.etl.tasks.scheduler.EtlJobLogDAO"
    ) as mock_log_dao:
        from addons.etl.tasks.scheduler import prune_log

        prune_log()
        mock_log_dao.prune_all_old_logs.assert_not_called()


@patch("addons.etl.tasks.scheduler.is_feature_enabled", return_value=True)
@patch("addons.etl.tasks.scheduler.EtlJobLogDAO")
def test_prune_log_calls_prune_all(
    mock_log_dao: MagicMock,
    mock_flag: MagicMock,
) -> None:
    mock_log_dao.prune_all_old_logs.return_value = 17

    from addons.etl.tasks.scheduler import prune_log

    prune_log()
    mock_log_dao.prune_all_old_logs.assert_called_once()
