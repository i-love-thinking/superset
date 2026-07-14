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
ExecuteEtlJobCommand

Downloads files from all EtlJobSource URLs, concatenates the resulting
DataFrames and writes them to the configured target database table.

Column post-processing pipeline (applied in order):
  1. columns_read   – keep only the listed columns
  2. column_rename  – rename columns according to the mapping
  3. column_data_types – cast columns to the specified pandas dtypes
     (reuses CSVReader._cast_column_types for consistent error messages)
"""
from __future__ import annotations

import io
import ipaddress
import logging
import socket
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

import pandas as pd
import requests
from flask import current_app
from flask_babel import lazy_gettext as _
from werkzeug.datastructures import FileStorage

from superset.commands.base import BaseCommand
from superset.commands.database.uploaders.csv_reader import CSVReader
from superset.commands.database.uploaders.excel_reader import ExcelReader
from superset.daos.database import DatabaseDAO
from superset.sql.parse import Table

from addons.etl.commands.exceptions import (
    EtlJobExecuteFailedError,
    EtlJobNotFoundError,
    EtlJobUrlNotAllowedError,
)
from addons.etl.daos.etl import EtlJobDAO, EtlJobLogDAO
from addons.etl.models import (
    EtlFileType,
    EtlJob,
    EtlJobLog,
    EtlJobSource,
    EtlScheduleType,
    EtlState,
)
from addons.etl.utils import validate_source_urls

logger = logging.getLogger(__name__)

# Number of rows to write per SQLAlchemy batch
_CHUNK_SIZE = 1000


class ExecuteEtlJobCommand(BaseCommand):
    """
    Fetch remote files and import them into the configured target database.

    Parameters
    ----------
    job_id:
        Primary key of the EtlJob to execute.
    scheduled_dttm:
        Optional ISO-string representing the scheduler's intended execution time
        (used for auditing/log association only; may be None for manual triggers).
    celery_task_id:
        Optional Celery task UUID (stored in EtlJobLog.celery_task_id).
    """

    def __init__(
        self,
        job_id: int,
        scheduled_dttm: Optional[datetime] = None,
        celery_task_id: Optional[str] = None,
    ) -> None:
        self._job_id = job_id
        self._scheduled_dttm = scheduled_dttm
        self._celery_task_id = celery_task_id

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> EtlJobLog:
        self.validate()
        job = EtlJobDAO.find_by_id(self._job_id)
        if not job:
            raise EtlJobNotFoundError()

        log = EtlJobLogDAO.create_log(
            job.id,
            scheduled_dttm=self._scheduled_dttm,
            celery_task_id=self._celery_task_id,
        )

        try:
            rows = self._execute(job)
            EtlJobLogDAO.update_log(log, EtlState.SUCCESS, rows_imported=rows)
            EtlJobDAO.update_last_run(job.id, EtlState.SUCCESS)

            # Deactivate one-time jobs after successful execution
            if job.schedule_type == EtlScheduleType.ONETIME:
                EtlJobDAO.deactivate(job.id)

        except Exception as ex:  # pylint: disable=broad-except
            error_msg = str(ex)
            logger.exception(
                "ETL job %s (%s) failed: %s", job.id, job.name, error_msg
            )
            EtlJobLogDAO.update_log(log, EtlState.ERROR, error_message=error_msg)
            EtlJobDAO.update_last_run(job.id, EtlState.ERROR)
            raise EtlJobExecuteFailedError() from ex

        return log

    def validate(self) -> None:
        if not EtlJobDAO.find_by_id(self._job_id):
            raise EtlJobNotFoundError()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute(self, job: EtlJob) -> int:
        """Download, combine, post-process, and write; return rows written."""
        import superset.utils.json as json

        # ── 1. Download all sources ────────────────────────────────────
        conn_params: dict[str, str] = {}
        if job.http_headers:
            conn_params = json.loads(job.http_headers)

        dfs: list[pd.DataFrame] = []
        for source in job.sources:
            df = self._fetch_source(source, job, conn_params)
            dfs.append(df)

        if not dfs:
            raise EtlJobExecuteFailedError()

        # ── 2. Concatenate ─────────────────────────────────────────────
        combined: pd.DataFrame = (
            pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
        )

        # ── 3. Column filtering ────────────────────────────────────────
        if job.columns_read:
            cols: list[str] = json.loads(job.columns_read)
            missing = [c for c in cols if c not in combined.columns]
            if missing:
                logger.warning(
                    "ETL job %s: columns_read references unknown columns: %s",
                    job.id,
                    missing,
                )
            combined = combined[[c for c in cols if c in combined.columns]]

        # ── 4. Column renaming ─────────────────────────────────────────
        if job.column_rename:
            rename_map: dict[str, str] = json.loads(job.column_rename)
            combined = combined.rename(columns=rename_map)

        # ── 5. Column type casting ─────────────────────────────────────
        if job.column_data_types:
            types: dict[str, str] = json.loads(job.column_data_types)
            # Reuse CSVReader's helper for consistent error messages
            combined = CSVReader._cast_column_types(combined, types, {})

        # ── 6. Write to target database ────────────────────────────────
        database = DatabaseDAO.find_by_id(job.database_id)
        if not database:
            raise EtlJobExecuteFailedError()

        data_table = Table(table=job.target_table, schema=job.target_schema)
        database.db_engine_spec.df_to_sql(
            database,
            data_table,
            combined,
            to_sql_kwargs={
                "chunksize": _CHUNK_SIZE,
                "if_exists": job.if_exists,
                "index": job.dataframe_index,
            },
        )

        return len(combined)

    def _fetch_source(
        self,
        source: EtlJobSource,
        job: EtlJob,
        conn_params: dict[str, str],
    ) -> pd.DataFrame:
        """Dispatch to the correct fetch helper based on URL scheme."""
        try:
            validate_source_urls([source.url])
        except ValueError as ex:
            raise EtlJobUrlNotAllowedError() from ex

        from urllib.parse import urlparse as _up
        scheme = _up(source.url).scheme.lower()

        if scheme == "smb":
            return self._fetch_smb_source(source, job, conn_params)
        return self._fetch_http_source(source, job, conn_params)

    def _fetch_http_source(
        self,
        source: EtlJobSource,
        job: EtlJob,
        http_headers: dict[str, str],
    ) -> pd.DataFrame:
        """Download one HTTP/HTTPS URL and return it as a DataFrame."""
        # Strip SMB-specific keys so they are not sent as HTTP headers
        safe_headers = {
            k: v
            for k, v in http_headers.items()
            if not k.startswith("smb_")
        }
        timeout = current_app.config.get("ETL_REQUEST_TIMEOUT_SECONDS", 60)
        response = requests.get(  # noqa: S113
            source.url,
            headers=safe_headers,
            timeout=timeout,
            stream=False,
        )
        response.raise_for_status()

        file_content = response.content
        file_type = self._detect_file_type(job.file_type, source.url, response)

        file_storage = FileStorage(
            stream=io.BytesIO(file_content),
            filename=source.url.split("?")[0].split("/")[-1] or "data",
        )

        if file_type == EtlFileType.EXCEL:
            return self._read_excel(file_storage, source, job)
        return self._read_csv_tsv(file_storage, source, job, file_type)

    @staticmethod
    def _fetch_smb_source(
        source: EtlJobSource,
        job: EtlJob,
        conn_params: dict[str, str],
    ) -> pd.DataFrame:
        """
        Download a file from an SMB share and return it as a DataFrame.

        URL format: smb://server/share/path/to/file.csv
        Credentials are read from conn_params:
          smb_username, smb_password, smb_domain (optional)
        """
        try:
            import smbclient  # type: ignore[import-untyped]
        except ImportError as exc:
            raise EtlJobExecuteFailedError() from ImportError(
                "smbprotocol is required for SMB support: "
                "pip install smbprotocol"
            )

        parsed = urlparse(source.url)
        server = parsed.hostname or ""
        # parsed.path is like /share/subdir/file.csv
        path_parts = parsed.path.lstrip("/").split("/", 1)
        share = path_parts[0]
        rel_path = path_parts[1].replace("/", "\\") if len(path_parts) > 1 else ""
        unc_path = f"\\\\{server}\\{share}\\{rel_path}"

        username = conn_params.get("smb_username")
        password = conn_params.get("smb_password", "")
        domain = conn_params.get("smb_domain", "")
        port = int(conn_params.get("smb_port", 445))

        if username:
            smbclient.register_session(
                server,
                username=username,
                password=password,
                domain=domain,
                port=port,
            )

        with smbclient.open_file(unc_path, mode="rb") as smb_file:
            file_content = smb_file.read()

        file_type = ExecuteEtlJobCommand._detect_file_type_from_path(
            job.file_type, source.url
        )
        file_storage = FileStorage(
            stream=io.BytesIO(file_content),
            filename=unc_path.split("\\")[-1] or "data",
        )

        if file_type == EtlFileType.EXCEL:
            return ExecuteEtlJobCommand._read_excel(file_storage, source, job)
        return ExecuteEtlJobCommand._read_csv_tsv(file_storage, source, job, file_type)

    # ------------------------------------------------------------------
    # Reader helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_file_type(
        job_file_type: str,
        url: str,
        response: requests.Response,
    ) -> str:
        if job_file_type != EtlFileType.AUTO:
            return job_file_type

        # Try Content-Type header first
        content_type = response.headers.get("Content-Type", "").lower()
        if "spreadsheet" in content_type or "excel" in content_type or "xlsx" in content_type:
            return EtlFileType.EXCEL
        if "tab-separated" in content_type or "tsv" in content_type:
            return EtlFileType.TSV

        return ExecuteEtlJobCommand._detect_file_type_from_path(job_file_type, url)

    @staticmethod
    def _detect_file_type_from_path(job_file_type: str, url: str) -> str:
        """Detect file type from URL path extension only (no HTTP response)."""
        if job_file_type != EtlFileType.AUTO:
            return job_file_type

        path = urlparse(url).path.lower().split("?")[0]
        if path.endswith(".xlsx") or path.endswith(".xls"):
            return EtlFileType.EXCEL
        if path.endswith(".tsv"):
            return EtlFileType.TSV

        # Default to CSV
        return EtlFileType.CSV

    @staticmethod
    def _read_excel(
        file_storage: FileStorage,
        source: EtlJobSource,
        job: EtlJob,
    ) -> pd.DataFrame:
        options: dict[str, Any] = {}
        if source.sheet_name:
            options["sheet_name"] = source.sheet_name
        reader = ExcelReader(options=options)
        return reader.file_to_dataframe(file_storage)

    @staticmethod
    def _read_csv_tsv(
        file_storage: FileStorage,
        source: EtlJobSource,
        job: EtlJob,
        file_type: str,
    ) -> pd.DataFrame:
        options: dict[str, Any] = {}

        # Determine delimiter
        if source.delimiter:
            options["delimiter"] = source.delimiter
        elif file_type == EtlFileType.TSV:
            options["delimiter"] = "\t"

        # Encoding override
        if source.encoding:
            # CSVReader handles this via the 'encoding' option (not standard
            # CSVReaderOptions, but read_csv accepts it directly)
            options["encoding"] = source.encoding

        reader = CSVReader(options=options)
        return reader.file_to_dataframe(file_storage)
