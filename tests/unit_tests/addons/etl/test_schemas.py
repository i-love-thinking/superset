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
Unit tests for Marshmallow schemas in addons/etl/schemas.py.
"""
from __future__ import annotations

import pytest
from marshmallow import ValidationError

from addons.etl.schemas import EtlJobPostSchema, EtlJobPutSchema, EtlJobSourceSchema


# ---------------------------------------------------------------------------
# EtlJobSourceSchema
# ---------------------------------------------------------------------------


def test_source_schema_valid_http() -> None:
    data = EtlJobSourceSchema().load({"url": "https://example.com/data.csv"})
    assert data["url"] == "https://example.com/data.csv"
    assert data["order"] == 0


def test_source_schema_valid_smb() -> None:
    data = EtlJobSourceSchema().load({"url": "smb://server/share/file.xlsx"})
    assert data["url"] == "smb://server/share/file.xlsx"


def test_source_schema_invalid_scheme_raises() -> None:
    with pytest.raises(ValidationError, match="must start with"):
        EtlJobSourceSchema().load({"url": "ftp://example.com/data.csv"})


def test_source_schema_missing_url_raises() -> None:
    with pytest.raises(ValidationError):
        EtlJobSourceSchema().load({})


def test_source_schema_optional_fields_default_none() -> None:
    data = EtlJobSourceSchema().load({"url": "https://example.com/data.csv"})
    assert data["sheet_name"] is None
    assert data["delimiter"] is None
    assert data["encoding"] is None


# ---------------------------------------------------------------------------
# EtlJobPostSchema — required fields
# ---------------------------------------------------------------------------


def _minimal_payload() -> dict:
    return {
        "name": "my_job",
        "database_id": 1,
        "target_table": "my_table",
        "sources": [{"url": "https://example.com/data.csv"}],
    }


def test_post_schema_valid_minimal() -> None:
    data = EtlJobPostSchema().load(_minimal_payload())
    assert data["name"] == "my_job"
    assert data["active"] is True
    assert data["schedule_type"] == "cron"
    assert data["file_type"] == "auto"
    assert data["if_exists"] == "fail"


def test_post_schema_missing_name_raises() -> None:
    payload = _minimal_payload()
    del payload["name"]
    with pytest.raises(ValidationError):
        EtlJobPostSchema().load(payload)


def test_post_schema_missing_database_id_raises() -> None:
    payload = _minimal_payload()
    del payload["database_id"]
    with pytest.raises(ValidationError):
        EtlJobPostSchema().load(payload)


def test_post_schema_missing_target_table_raises() -> None:
    payload = _minimal_payload()
    del payload["target_table"]
    with pytest.raises(ValidationError):
        EtlJobPostSchema().load(payload)


def test_post_schema_empty_sources_raises() -> None:
    payload = {**_minimal_payload(), "sources": []}
    with pytest.raises(ValidationError):
        EtlJobPostSchema().load(payload)


def test_post_schema_invalid_schedule_type_raises() -> None:
    payload = {**_minimal_payload(), "schedule_type": "daily"}
    with pytest.raises(ValidationError):
        EtlJobPostSchema().load(payload)


def test_post_schema_invalid_if_exists_raises() -> None:
    payload = {**_minimal_payload(), "if_exists": "upsert"}
    with pytest.raises(ValidationError):
        EtlJobPostSchema().load(payload)


def test_post_schema_invalid_file_type_raises() -> None:
    payload = {**_minimal_payload(), "file_type": "parquet"}
    with pytest.raises(ValidationError):
        EtlJobPostSchema().load(payload)


def test_post_schema_all_file_types_valid() -> None:
    for ft in ("auto", "csv", "tsv", "excel"):
        data = EtlJobPostSchema().load({**_minimal_payload(), "file_type": ft})
        assert data["file_type"] == ft


def test_post_schema_onetime_schedule() -> None:
    payload = {
        **_minimal_payload(),
        "schedule_type": "onetime",
        "run_at": "2026-08-01T10:00:00",
    }
    data = EtlJobPostSchema().load(payload)
    assert data["schedule_type"] == "onetime"
    assert data["run_at"] is not None


def test_post_schema_log_retention_too_low_raises() -> None:
    payload = {**_minimal_payload(), "log_retention": 0}
    with pytest.raises(ValidationError):
        EtlJobPostSchema().load(payload)


def test_post_schema_working_timeout_too_low_raises() -> None:
    payload = {**_minimal_payload(), "working_timeout": 30}
    with pytest.raises(ValidationError):
        EtlJobPostSchema().load(payload)


# ---------------------------------------------------------------------------
# EtlJobPutSchema — all fields optional
# ---------------------------------------------------------------------------


def test_put_schema_empty_body_valid() -> None:
    """PUT with empty body should not raise — all fields are optional."""
    data = EtlJobPutSchema().load({})
    assert data == {}


def test_put_schema_partial_update() -> None:
    data = EtlJobPutSchema().load({"active": False, "crontab": "0 6 * * *"})
    assert data["active"] is False
    assert data["crontab"] == "0 6 * * *"
