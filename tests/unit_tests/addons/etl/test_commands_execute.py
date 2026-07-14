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
Unit tests for ExecuteEtlJobCommand — file download, post-processing,
file-type detection, SMB fetching, and error handling.
"""
from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from werkzeug.datastructures import FileStorage

from addons.etl.commands.exceptions import (
    EtlJobExecuteFailedError,
    EtlJobNotFoundError,
    EtlJobUrlNotAllowedError,
)
from addons.etl.models import EtlFileType, EtlIfExists, EtlScheduleType, EtlState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(
    url: str = "https://example.com/data.csv",
    sheet_name: str | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
) -> MagicMock:
    s = MagicMock()
    s.url = url
    s.sheet_name = sheet_name
    s.delimiter = delimiter
    s.encoding = encoding
    return s


def _make_job(
    sources: list[MagicMock] | None = None,
    file_type: str = EtlFileType.AUTO,
    columns_read: str | None = None,
    column_data_types: str | None = None,
    column_rename: str | None = None,
    http_headers: str | None = None,
    if_exists: str = EtlIfExists.FAIL,
    schedule_type: str = EtlScheduleType.CRON,
) -> MagicMock:
    job = MagicMock()
    job.id = 1
    job.name = "test_job"
    job.database_id = 1
    job.target_schema = None
    job.target_table = "test_table"
    job.file_type = file_type
    job.if_exists = if_exists
    job.dataframe_index = False
    job.columns_read = columns_read
    job.column_data_types = column_data_types
    job.column_rename = column_rename
    job.http_headers = http_headers
    job.log_retention = 90
    job.working_timeout = 3600
    job.schedule_type = schedule_type
    job.sources = sources or [_make_source()]
    return job


def _csv_bytes(rows: list[list[str]]) -> bytes:
    import csv
    from io import StringIO

    buf = StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


# ===========================================================================
# _detect_file_type (HTTP response-based)
# ===========================================================================


def test_detect_file_type_returns_explicit_type() -> None:
    from addons.etl.commands.execute import ExecuteEtlJobCommand

    response = MagicMock()
    assert (
        ExecuteEtlJobCommand._detect_file_type(EtlFileType.CSV, "http://x.com/f", response)
        == EtlFileType.CSV
    )
    assert (
        ExecuteEtlJobCommand._detect_file_type(EtlFileType.EXCEL, "http://x.com/f", response)
        == EtlFileType.EXCEL
    )


def test_detect_file_type_auto_from_content_type_xlsx() -> None:
    from addons.etl.commands.execute import ExecuteEtlJobCommand

    response = MagicMock()
    response.headers = {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }
    result = ExecuteEtlJobCommand._detect_file_type(
        EtlFileType.AUTO, "http://x.com/file", response
    )
    assert result == EtlFileType.EXCEL


def test_detect_file_type_auto_from_content_type_tsv() -> None:
    from addons.etl.commands.execute import ExecuteEtlJobCommand

    response = MagicMock()
    response.headers = {"Content-Type": "text/tab-separated-values"}
    result = ExecuteEtlJobCommand._detect_file_type(
        EtlFileType.AUTO, "http://x.com/file", response
    )
    assert result == EtlFileType.TSV


def test_detect_file_type_auto_falls_back_to_csv() -> None:
    from addons.etl.commands.execute import ExecuteEtlJobCommand

    response = MagicMock()
    response.headers = {"Content-Type": "application/octet-stream"}
    result = ExecuteEtlJobCommand._detect_file_type(
        EtlFileType.AUTO, "http://x.com/file", response
    )
    assert result == EtlFileType.CSV


# ===========================================================================
# _detect_file_type_from_path (URL extension, no HTTP response)
# ===========================================================================


def test_detect_file_type_from_path_xlsx() -> None:
    from addons.etl.commands.execute import ExecuteEtlJobCommand

    assert (
        ExecuteEtlJobCommand._detect_file_type_from_path(
            EtlFileType.AUTO, "smb://server/share/report.xlsx"
        )
        == EtlFileType.EXCEL
    )


def test_detect_file_type_from_path_xls() -> None:
    from addons.etl.commands.execute import ExecuteEtlJobCommand

    assert (
        ExecuteEtlJobCommand._detect_file_type_from_path(
            EtlFileType.AUTO, "smb://server/share/report.xls"
        )
        == EtlFileType.EXCEL
    )


def test_detect_file_type_from_path_tsv() -> None:
    from addons.etl.commands.execute import ExecuteEtlJobCommand

    assert (
        ExecuteEtlJobCommand._detect_file_type_from_path(
            EtlFileType.AUTO, "smb://server/share/data.tsv"
        )
        == EtlFileType.TSV
    )


def test_detect_file_type_from_path_defaults_csv() -> None:
    from addons.etl.commands.execute import ExecuteEtlJobCommand

    assert (
        ExecuteEtlJobCommand._detect_file_type_from_path(
            EtlFileType.AUTO, "smb://server/share/data.txt"
        )
        == EtlFileType.CSV
    )


def test_detect_file_type_from_path_explicit_type_wins() -> None:
    from addons.etl.commands.execute import ExecuteEtlJobCommand

    assert (
        ExecuteEtlJobCommand._detect_file_type_from_path(
            EtlFileType.TSV, "smb://server/share/data.csv"
        )
        == EtlFileType.TSV
    )


# ===========================================================================
# Column post-processing (_execute internals mocked)
# ===========================================================================


def _run_execute_with_df(df: pd.DataFrame, job: MagicMock) -> int:
    """
    Patch all I/O so that _execute receives a pre-built DataFrame and returns
    the number of rows written.
    """
    with (
        patch(
            "addons.etl.commands.execute.EtlJobDAO.find_by_id", return_value=job
        ),
        patch(
            "addons.etl.commands.execute.EtlJobLogDAO.create_log",
            return_value=MagicMock(),
        ),
        patch(
            "addons.etl.commands.execute.EtlJobLogDAO.update_log"
        ),
        patch(
            "addons.etl.commands.execute.EtlJobDAO.update_last_run"
        ),
        patch(
            "addons.etl.commands.execute.ExecuteEtlJobCommand._fetch_source",
            return_value=df,
        ),
        patch(
            "addons.etl.commands.execute.DatabaseDAO.find_by_id",
            return_value=MagicMock(),
        ),
    ):
        from addons.etl.commands.execute import ExecuteEtlJobCommand

        cmd = ExecuteEtlJobCommand(job_id=1)
        cmd.run()
        # Return len via side-channel inspection of df_to_sql call
        return len(df)


def test_execute_columns_read_filters_columns() -> None:
    df_full = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
    job = _make_job(columns_read=json.dumps(["a", "b"]))

    with (
        patch(
            "addons.etl.commands.execute.EtlJobDAO.find_by_id", return_value=job
        ),
        patch(
            "addons.etl.commands.execute.EtlJobLogDAO.create_log",
            return_value=MagicMock(),
        ),
        patch("addons.etl.commands.execute.EtlJobLogDAO.update_log"),
        patch("addons.etl.commands.execute.EtlJobDAO.update_last_run"),
        patch(
            "addons.etl.commands.execute.ExecuteEtlJobCommand._fetch_source",
            return_value=df_full,
        ),
        patch(
            "addons.etl.commands.execute.DatabaseDAO.find_by_id",
            return_value=MagicMock(),
        ) as mock_db_find,
    ):
        captured: dict[str, Any] = {}

        def capture_df_to_sql(database, table, df, to_sql_kwargs):
            captured["df"] = df

        mock_db_find.return_value.db_engine_spec.df_to_sql = capture_df_to_sql

        from addons.etl.commands.execute import ExecuteEtlJobCommand

        ExecuteEtlJobCommand(job_id=1).run()

    assert list(captured["df"].columns) == ["a", "b"]
    assert "c" not in captured["df"].columns


def test_execute_column_rename_renames_columns() -> None:
    df_in = pd.DataFrame({"old_name": [1, 2], "keep": ["x", "y"]})
    job = _make_job(column_rename=json.dumps({"old_name": "new_name"}))

    with (
        patch("addons.etl.commands.execute.EtlJobDAO.find_by_id", return_value=job),
        patch(
            "addons.etl.commands.execute.EtlJobLogDAO.create_log",
            return_value=MagicMock(),
        ),
        patch("addons.etl.commands.execute.EtlJobLogDAO.update_log"),
        patch("addons.etl.commands.execute.EtlJobDAO.update_last_run"),
        patch(
            "addons.etl.commands.execute.ExecuteEtlJobCommand._fetch_source",
            return_value=df_in,
        ),
        patch(
            "addons.etl.commands.execute.DatabaseDAO.find_by_id",
            return_value=MagicMock(),
        ) as mock_db_find,
    ):
        captured: dict[str, Any] = {}

        def capture_df_to_sql(database, table, df, to_sql_kwargs):
            captured["df"] = df

        mock_db_find.return_value.db_engine_spec.df_to_sql = capture_df_to_sql

        from addons.etl.commands.execute import ExecuteEtlJobCommand

        ExecuteEtlJobCommand(job_id=1).run()

    assert "new_name" in captured["df"].columns
    assert "old_name" not in captured["df"].columns


def test_execute_multiple_sources_are_concatenated() -> None:
    df1 = pd.DataFrame({"x": [1, 2]})
    df2 = pd.DataFrame({"x": [3, 4]})
    job = _make_job(sources=[_make_source(), _make_source()])

    with (
        patch("addons.etl.commands.execute.EtlJobDAO.find_by_id", return_value=job),
        patch(
            "addons.etl.commands.execute.EtlJobLogDAO.create_log",
            return_value=MagicMock(),
        ),
        patch("addons.etl.commands.execute.EtlJobLogDAO.update_log"),
        patch("addons.etl.commands.execute.EtlJobDAO.update_last_run"),
        patch(
            "addons.etl.commands.execute.ExecuteEtlJobCommand._fetch_source",
            side_effect=[df1, df2],
        ),
        patch(
            "addons.etl.commands.execute.DatabaseDAO.find_by_id",
            return_value=MagicMock(),
        ) as mock_db_find,
    ):
        captured: dict[str, Any] = {}

        def capture_df_to_sql(database, table, df, to_sql_kwargs):
            captured["df"] = df

        mock_db_find.return_value.db_engine_spec.df_to_sql = capture_df_to_sql

        from addons.etl.commands.execute import ExecuteEtlJobCommand

        ExecuteEtlJobCommand(job_id=1).run()

    assert len(captured["df"]) == 4
    assert list(captured["df"]["x"]) == [1, 2, 3, 4]


def test_execute_logs_error_and_reraises_on_failure() -> None:
    job = _make_job()

    with (
        patch("addons.etl.commands.execute.EtlJobDAO.find_by_id", return_value=job),
        patch(
            "addons.etl.commands.execute.EtlJobLogDAO.create_log",
            return_value=MagicMock(),
        ),
        patch("addons.etl.commands.execute.EtlJobLogDAO.update_log") as mock_update_log,
        patch("addons.etl.commands.execute.EtlJobDAO.update_last_run"),
        patch(
            "addons.etl.commands.execute.ExecuteEtlJobCommand._fetch_source",
            side_effect=RuntimeError("network failure"),
        ),
    ):
        from addons.etl.commands.execute import ExecuteEtlJobCommand

        with pytest.raises(EtlJobExecuteFailedError):
            ExecuteEtlJobCommand(job_id=1).run()

        # The log should have been updated with ERROR state
        update_call_args = mock_update_log.call_args
        assert update_call_args[0][1] == EtlState.ERROR
        assert "network failure" in update_call_args[1].get("error_message", "") or \
               "network failure" in str(update_call_args[0])


def test_execute_raises_not_found_when_job_missing() -> None:
    with patch(
        "addons.etl.commands.execute.EtlJobDAO.find_by_id", return_value=None
    ):
        from addons.etl.commands.execute import ExecuteEtlJobCommand

        with pytest.raises(EtlJobNotFoundError):
            ExecuteEtlJobCommand(job_id=999).run()


def test_execute_deactivates_onetime_job_after_success() -> None:
    job = _make_job(schedule_type=EtlScheduleType.ONETIME)

    with (
        patch("addons.etl.commands.execute.EtlJobDAO.find_by_id", return_value=job),
        patch(
            "addons.etl.commands.execute.EtlJobLogDAO.create_log",
            return_value=MagicMock(),
        ),
        patch("addons.etl.commands.execute.EtlJobLogDAO.update_log"),
        patch(
            "addons.etl.commands.execute.EtlJobDAO.update_last_run"
        ),
        patch(
            "addons.etl.commands.execute.EtlJobDAO.deactivate"
        ) as mock_deactivate,
        patch(
            "addons.etl.commands.execute.ExecuteEtlJobCommand._fetch_source",
            return_value=pd.DataFrame({"x": [1]}),
        ),
        patch(
            "addons.etl.commands.execute.DatabaseDAO.find_by_id",
            return_value=MagicMock(),
        ),
    ):
        from addons.etl.commands.execute import ExecuteEtlJobCommand

        ExecuteEtlJobCommand(job_id=1).run()

    mock_deactivate.assert_called_once_with(1)


# ===========================================================================
# HTTP source fetching
# ===========================================================================


def test_fetch_http_source_strips_smb_keys_from_headers() -> None:
    """smb_* keys must not be forwarded as HTTP request headers."""
    import responses as resp_lib

    job = _make_job()
    conn_params = {
        "Authorization": "Bearer tok",
        "smb_username": "user",
        "smb_password": "pass",
    }

    csv_content = _csv_bytes([["a", "b"], ["1", "2"]])

    with patch("addons.etl.commands.execute.validate_source_urls"), \
         patch("addons.etl.commands.execute.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.content = csv_content
        mock_response.headers = {"Content-Type": "text/csv"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        from addons.etl.commands.execute import ExecuteEtlJobCommand

        source = _make_source(url="https://example.com/data.csv")
        ExecuteEtlJobCommand._fetch_http_source.__func__(
            None, source, job, conn_params
        )

        # Check that smb_ keys were stripped from the request
        actual_headers = mock_get.call_args[1]["headers"]
        assert "smb_username" not in actual_headers
        assert "smb_password" not in actual_headers
        assert actual_headers.get("Authorization") == "Bearer tok"


def test_fetch_source_raises_url_not_allowed_for_bad_scheme() -> None:
    from addons.etl.commands.execute import ExecuteEtlJobCommand

    source = _make_source(url="ftp://bad.example.com/data.csv")
    job = _make_job(sources=[source])
    cmd = ExecuteEtlJobCommand(job_id=1)

    with patch(
        "addons.etl.commands.execute.validate_source_urls",
        side_effect=ValueError("scheme not allowed"),
    ):
        with pytest.raises(EtlJobUrlNotAllowedError):
            cmd._fetch_source(source, job, {})


# ===========================================================================
# SMB source fetching
# ===========================================================================


def test_fetch_smb_source_builds_correct_unc_path() -> None:
    csv_content = _csv_bytes([["col"], ["val"]])

    mock_smb_module = MagicMock()
    mock_smb_module.open_file.return_value.__enter__ = lambda s: io.BytesIO(csv_content)
    mock_smb_module.open_file.return_value.__exit__ = MagicMock(return_value=False)

    source = _make_source(url="smb://fileserver/share/subdir/data.csv")
    job = _make_job(file_type=EtlFileType.CSV)
    conn_params = {"smb_username": "domain\\user", "smb_password": "secret"}

    with patch.dict("sys.modules", {"smbclient": mock_smb_module}):
        from addons.etl.commands.execute import ExecuteEtlJobCommand

        ExecuteEtlJobCommand._fetch_smb_source(source, job, conn_params)

        # Verify register_session was called with the correct server
        mock_smb_module.register_session.assert_called_once()
        call_args = mock_smb_module.register_session.call_args
        assert call_args[0][0] == "fileserver"
        assert call_args[1]["username"] == "domain\\user"
        assert call_args[1]["password"] == "secret"

        # Verify open_file received a UNC path
        open_call = mock_smb_module.open_file.call_args[0][0]
        assert open_call.startswith("\\\\fileserver\\share\\")
        assert "subdir" in open_call
        assert "data.csv" in open_call


def test_fetch_smb_source_skips_register_when_no_credentials() -> None:
    csv_content = _csv_bytes([["col"], ["val"]])

    mock_smb_module = MagicMock()
    mock_smb_module.open_file.return_value.__enter__ = lambda s: io.BytesIO(csv_content)
    mock_smb_module.open_file.return_value.__exit__ = MagicMock(return_value=False)

    source = _make_source(url="smb://fileserver/share/data.csv")
    job = _make_job(file_type=EtlFileType.CSV)

    with patch.dict("sys.modules", {"smbclient": mock_smb_module}):
        from addons.etl.commands.execute import ExecuteEtlJobCommand

        ExecuteEtlJobCommand._fetch_smb_source(source, job, {})

        mock_smb_module.register_session.assert_not_called()


def test_fetch_smb_source_raises_when_smbprotocol_missing() -> None:
    import sys

    source = _make_source(url="smb://fileserver/share/data.csv")
    job = _make_job()

    with patch.dict("sys.modules", {"smbclient": None}):
        # Force ImportError by temporarily removing smbclient if loaded
        original = sys.modules.pop("smbclient", None)
        try:
            from addons.etl.commands.execute import ExecuteEtlJobCommand

            with pytest.raises(EtlJobExecuteFailedError):
                ExecuteEtlJobCommand._fetch_smb_source(source, job, {})
        finally:
            if original is not None:
                sys.modules["smbclient"] = original
