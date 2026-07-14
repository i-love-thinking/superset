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
Unit tests for EtlJobDAO and EtlJobLogDAO.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from addons.etl.models import EtlScheduleType, EtlState


# ---------------------------------------------------------------------------
# EtlJobDAO
# ---------------------------------------------------------------------------


@patch("addons.etl.daos.etl.db")
def test_find_by_id_returns_job(mock_db: MagicMock) -> None:
    from addons.etl.daos.etl import EtlJobDAO
    from addons.etl.models import EtlJob

    mock_job = MagicMock(spec=EtlJob)
    mock_db.session.query.return_value.filter_by.return_value.one_or_none.return_value = (
        mock_job
    )

    result = EtlJobDAO.find_by_id(1)
    assert result is mock_job


@patch("addons.etl.daos.etl.db")
def test_find_by_id_returns_none_when_not_found(mock_db: MagicMock) -> None:
    from addons.etl.daos.etl import EtlJobDAO

    mock_db.session.query.return_value.filter_by.return_value.one_or_none.return_value = (
        None
    )

    assert EtlJobDAO.find_by_id(999) is None


@patch("addons.etl.daos.etl.db")
def test_find_active_cron_filters_correctly(mock_db: MagicMock) -> None:
    from addons.etl.daos.etl import EtlJobDAO
    from addons.etl.models import EtlJob

    mock_jobs = [MagicMock(spec=EtlJob)]
    (
        mock_db.session.query.return_value.filter.return_value.all.return_value
    ) = mock_jobs

    result = EtlJobDAO.find_active_cron()
    assert result == mock_jobs


@patch("addons.etl.daos.etl.db")
def test_find_due_onetime_filters_by_run_at(mock_db: MagicMock) -> None:
    from addons.etl.daos.etl import EtlJobDAO
    from addons.etl.models import EtlJob

    mock_jobs = [MagicMock(spec=EtlJob)]
    (
        mock_db.session.query.return_value.filter.return_value.all.return_value
    ) = mock_jobs

    now = datetime(2026, 7, 15, 12, 0, 0)
    result = EtlJobDAO.find_due_onetime(now)
    assert result == mock_jobs


@patch("addons.etl.daos.etl.db")
def test_update_last_run_updates_fields(mock_db: MagicMock) -> None:
    from addons.etl.daos.etl import EtlJobDAO

    EtlJobDAO.update_last_run(1, EtlState.SUCCESS)

    mock_db.session.query.return_value.filter_by.return_value.update.assert_called_once()
    call_kwargs = (
        mock_db.session.query.return_value.filter_by.return_value.update.call_args[0][
            0
        ]
    )
    assert call_kwargs["last_run_state"] == EtlState.SUCCESS
    assert "last_run_dttm" in call_kwargs


@patch("addons.etl.daos.etl.db")
def test_deactivate_sets_active_false(mock_db: MagicMock) -> None:
    from addons.etl.daos.etl import EtlJobDAO

    EtlJobDAO.deactivate(1)

    mock_db.session.query.return_value.filter_by.return_value.update.assert_called_once_with(
        {"active": False}
    )


# ---------------------------------------------------------------------------
# EtlJobLogDAO
# ---------------------------------------------------------------------------


@patch("addons.etl.daos.etl.db")
def test_create_log_sets_working_state(mock_db: MagicMock) -> None:
    from addons.etl.daos.etl import EtlJobLogDAO
    from addons.etl.models import EtlJobLog

    log = EtlJobLogDAO.create_log(job_id=1, celery_task_id="task-123")

    mock_db.session.add.assert_called_once()
    added = mock_db.session.add.call_args[0][0]
    assert isinstance(added, EtlJobLog)
    assert added.etl_job_id == 1
    assert added.state == EtlState.WORKING
    assert added.celery_task_id == "task-123"


@patch("addons.etl.daos.etl.db")
def test_update_log_sets_end_time_and_state(mock_db: MagicMock) -> None:
    from addons.etl.daos.etl import EtlJobLogDAO
    from addons.etl.models import EtlJobLog

    log = MagicMock(spec=EtlJobLog)
    EtlJobLogDAO.update_log(log, EtlState.SUCCESS, rows_imported=42)

    assert log.state == EtlState.SUCCESS
    assert log.rows_imported == 42
    assert log.end_dttm is not None


@patch("addons.etl.daos.etl.db")
def test_update_log_captures_error_message(mock_db: MagicMock) -> None:
    from addons.etl.daos.etl import EtlJobLogDAO
    from addons.etl.models import EtlJobLog

    log = MagicMock(spec=EtlJobLog)
    EtlJobLogDAO.update_log(log, EtlState.ERROR, error_message="Connection refused")

    assert log.state == EtlState.ERROR
    assert log.error_message == "Connection refused"


@patch("addons.etl.daos.etl.db")
def test_find_by_job_returns_paginated_results(mock_db: MagicMock) -> None:
    from addons.etl.daos.etl import EtlJobLogDAO
    from addons.etl.models import EtlJobLog

    mock_logs = [MagicMock(spec=EtlJobLog) for _ in range(3)]
    query_chain = mock_db.session.query.return_value.filter_by.return_value
    query_chain.count.return_value = 3
    query_chain.order_by.return_value.offset.return_value.limit.return_value.all.return_value = (
        mock_logs
    )

    logs, total = EtlJobLogDAO.find_by_job(job_id=1, page=0, page_size=10)
    assert total == 3
    assert logs == mock_logs


@patch("addons.etl.daos.etl.db")
def test_prune_old_logs_deletes_by_cutoff(mock_db: MagicMock) -> None:
    from addons.etl.daos.etl import EtlJobLogDAO

    mock_db.session.query.return_value.filter.return_value.delete.return_value = 5

    deleted = EtlJobLogDAO.prune_old_logs(job_id=1, retention_days=30)
    assert deleted == 5
    mock_db.session.commit.assert_called_once()
