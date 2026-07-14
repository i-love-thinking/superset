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
Shared pytest fixtures for ETL addon unit tests.

These fixtures provide lightweight, fully-mocked ETL objects so that
individual test modules do not need a live database or application context.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from addons.etl.models import EtlFileType, EtlIfExists, EtlJob, EtlJobLog, EtlJobSource, EtlScheduleType, EtlState


# ---------------------------------------------------------------------------
# Raw property dicts (used to build commands / DAOs)
# ---------------------------------------------------------------------------


def make_source_props(
    url: str = "https://example.com/data.csv",
    order: int = 0,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    encoding: str | None = None,
) -> dict[str, Any]:
    return {
        "url": url,
        "order": order,
        "delimiter": delimiter,
        "sheet_name": sheet_name,
        "encoding": encoding,
    }


def make_job_props(
    name: str = "test_etl_job",
    database_id: int = 1,
    target_table: str = "test_table",
    schedule_type: str = EtlScheduleType.CRON,
    crontab: str = "0 * * * *",
    sources: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": "A test ETL job",
        "active": True,
        "schedule_type": schedule_type,
        "crontab": crontab,
        "run_at": None,
        "timezone": "UTC",
        "database_id": database_id,
        "target_schema": None,
        "target_table": target_table,
        "file_type": EtlFileType.AUTO,
        "if_exists": EtlIfExists.FAIL,
        "dataframe_index": False,
        "columns_read": None,
        "column_data_types": None,
        "column_rename": None,
        "http_headers": None,
        "log_retention": 90,
        "working_timeout": 3600,
        "sources": sources or [make_source_props()],
        **kwargs,
    }


# ---------------------------------------------------------------------------
# Mock model instances
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_source() -> EtlJobSource:
    source = MagicMock(spec=EtlJobSource)
    source.id = 1
    source.etl_job_id = 1
    source.url = "https://example.com/data.csv"
    source.order = 0
    source.sheet_name = None
    source.delimiter = None
    source.encoding = None
    return source


@pytest.fixture
def mock_etl_job(mock_source: EtlJobSource) -> EtlJob:
    job = MagicMock(spec=EtlJob)
    job.id = 1
    job.uuid = uuid4()
    job.name = "test_etl_job"
    job.description = "A test ETL job"
    job.active = True
    job.schedule_type = EtlScheduleType.CRON
    job.crontab = "0 * * * *"
    job.run_at = None
    job.timezone = "UTC"
    job.database_id = 1
    job.target_schema = None
    job.target_table = "test_table"
    job.file_type = EtlFileType.AUTO
    job.if_exists = EtlIfExists.FAIL
    job.dataframe_index = False
    job.columns_read = None
    job.column_data_types = None
    job.column_rename = None
    job.http_headers = None
    job.log_retention = 90
    job.working_timeout = 3600
    job.sources = [mock_source]
    job.last_run_dttm = None
    job.last_run_state = None
    return job


@pytest.fixture
def mock_etl_job_log(mock_etl_job: EtlJob) -> EtlJobLog:
    log = MagicMock(spec=EtlJobLog)
    log.id = 1
    log.etl_job_id = mock_etl_job.id
    log.scheduled_dttm = None
    log.start_dttm = datetime(2026, 7, 15, 0, 0, 0)
    log.end_dttm = None
    log.state = EtlState.WORKING
    log.error_message = None
    log.rows_imported = None
    log.celery_task_id = "celery-task-abc123"
    return log


@pytest.fixture
def mock_database() -> MagicMock:
    db = MagicMock()
    db.id = 1
    db.database_name = "test_db"
    db.db_engine_spec = MagicMock()
    db.db_engine_spec.df_to_sql = MagicMock()
    return db
