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
# KIND, differing express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import datetime
from typing import Any, Optional

from flask_appbuilder import Model
from flask_appbuilder.models.decorators import renders
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import backref, relationship
from sqlalchemy_utils import UUIDType

from superset.models.helpers import AuditMixinNullable, ExtraJSONMixin
from superset.utils.backports import StrEnum

logger = logging.getLogger(__name__)

metadata = Model.metadata  # pylint: disable=no-member


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class EtlScheduleType(StrEnum):
    CRON = "cron"
    ONETIME = "onetime"


class EtlFileType(StrEnum):
    AUTO = "auto"
    CSV = "csv"
    TSV = "tsv"
    EXCEL = "excel"


class EtlIfExists(StrEnum):
    FAIL = "fail"
    REPLACE = "replace"
    APPEND = "append"


class EtlState(StrEnum):
    SUCCESS = "success"
    WORKING = "working"
    ERROR = "error"
    PENDING = "pending"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EtlJob(AuditMixinNullable, ExtraJSONMixin, Model):
    """
    Represents a single ETL job configuration.

    A job holds one or more source URLs (EtlJobSource) from which CSV/TSV/Excel
    files are downloaded by a Celery worker, concatenated, optionally
    column-filtered/renamed/type-cast, and written to a Superset database.
    """

    __tablename__ = "etl_jobs"
    __table_args__ = (
        Index("ix_etl_jobs_active", "active"),
        Index("ix_etl_jobs_last_run_state", "last_run_state"),
    )

    id = Column(Integer, primary_key=True)
    uuid = Column(
        UUIDType(binary=True),
        default=uuid_lib.uuid4,
        unique=True,
        nullable=False,
    )
    name = Column(String(150), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)

    # ------------------------------------------------------------------
    # Schedule
    # ------------------------------------------------------------------
    schedule_type = Column(
        String(50), default=EtlScheduleType.CRON, nullable=False
    )
    crontab = Column(String(1000), nullable=True)
    """Cron expression used when schedule_type == 'cron'."""
    run_at = Column(DateTime, nullable=True)
    """Single fire-time used when schedule_type == 'onetime'."""
    timezone = Column(String(100), default="UTC", nullable=False)

    # ------------------------------------------------------------------
    # Target database
    # ------------------------------------------------------------------
    database_id = Column(Integer, ForeignKey("dbs.id"), nullable=False)
    database = relationship(
        "Database",
        backref=backref("etl_jobs", cascade="all, delete-orphan"),
        foreign_keys=[database_id],
    )
    target_schema = Column(String(250), nullable=True)
    target_table = Column(String(250), nullable=False)

    # ------------------------------------------------------------------
    # File options
    # ------------------------------------------------------------------
    file_type = Column(String(50), default=EtlFileType.AUTO, nullable=False)
    """
    auto  – detect from Content-Type header or URL extension
    csv   – force CSV reader
    tsv   – force CSV reader with tab delimiter
    excel – force Excel reader
    """
    if_exists = Column(String(50), default=EtlIfExists.FAIL, nullable=False)
    """Behaviour when the target table already exists: fail / replace / append."""
    dataframe_index = Column(Boolean, default=False, nullable=False)
    """Whether to write the DataFrame row index into the table."""

    # ------------------------------------------------------------------
    # Column options (stored as JSON text)
    # ------------------------------------------------------------------
    columns_read = Column(Text, nullable=True)
    """
    JSON list of column names to keep after reading the file.
    e.g. '["col_a", "col_b"]'
    If null, all columns are kept.
    """
    column_data_types = Column(Text, nullable=True)
    """
    JSON dict mapping column names to pandas dtypes.
    e.g. '{"amount": "float64", "category": "string"}'
    Applied after column filtering and renaming.
    """
    column_rename = Column(Text, nullable=True)
    """
    JSON dict mapping original column names to new names.
    e.g. '{"old_name": "new_name"}'
    Applied after column filtering.
    """

    # ------------------------------------------------------------------
    # HTTP options (stored as JSON text; values NOT encrypted by default)
    # ------------------------------------------------------------------
    http_headers = Column(Text, nullable=True)
    """
    JSON dict of HTTP request headers sent when downloading each source URL.
    e.g. '{"Authorization": "Bearer <token>"}'
    Store sensitive values in a secrets manager and reference them here,
    or rely on the operator-level network isolation.
    """

    # ------------------------------------------------------------------
    # Status tracking
    # ------------------------------------------------------------------
    last_run_dttm = Column(DateTime, nullable=True)
    last_run_state = Column(String(50), nullable=True)

    # ------------------------------------------------------------------
    # Operational limits
    # ------------------------------------------------------------------
    log_retention = Column(Integer, default=90, nullable=False)
    """Number of days to keep EtlJobLog rows for this job."""
    working_timeout = Column(Integer, default=3600, nullable=False)
    """Celery task soft-time-limit in seconds."""

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    sources = relationship(
        "EtlJobSource",
        back_populates="etl_job",
        cascade="all, delete-orphan",
        order_by="EtlJobSource.order",
    )
    logs = relationship(
        "EtlJobLog",
        back_populates="etl_job",
        cascade="all, delete-orphan",
    )

    @renders("name")
    def name_link(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"<EtlJob id={self.id} name={self.name!r}>"


class EtlJobSource(Model):
    """
    A single source URL belonging to an EtlJob.

    Multiple sources are downloaded sequentially and their DataFrames are
    concatenated (pd.concat with ignore_index=True) before being written
    to the target table.
    """

    __tablename__ = "etl_job_sources"
    __table_args__ = (Index("ix_etl_job_sources_etl_job_id", "etl_job_id"),)

    id = Column(Integer, primary_key=True)
    etl_job_id = Column(
        Integer,
        ForeignKey("etl_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    url = Column(String(2048), nullable=False)
    order = Column(Integer, default=0, nullable=False)

    # Per-source overrides
    sheet_name = Column(String(250), nullable=True)
    """Excel sheet name or index (used only for Excel files)."""
    delimiter = Column(String(10), nullable=True)
    """CSV/TSV delimiter character; defaults to ',' for CSV and '\\t' for TSV."""
    encoding = Column(String(50), nullable=True)
    """Force a specific character encoding; null = auto-detect."""

    # Relationship
    etl_job = relationship("EtlJob", back_populates="sources")

    def __repr__(self) -> str:
        return f"<EtlJobSource id={self.id} url={self.url!r}>"


class EtlJobLog(Model):
    """Execution history for an EtlJob."""

    __tablename__ = "etl_job_logs"
    __table_args__ = (
        Index("ix_etl_job_logs_etl_job_id", "etl_job_id"),
        Index("ix_etl_job_logs_state", "state"),
        Index("ix_etl_job_logs_start_dttm", "start_dttm"),
    )

    id = Column(Integer, primary_key=True)
    etl_job_id = Column(
        Integer,
        ForeignKey("etl_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    scheduled_dttm = Column(DateTime, nullable=True)
    """The time for which this execution was originally scheduled (may be null for manual triggers)."""
    start_dttm = Column(DateTime, nullable=False, default=datetime.utcnow)
    end_dttm = Column(DateTime, nullable=True)
    state = Column(String(50), nullable=False, default=EtlState.WORKING)
    error_message = Column(Text, nullable=True)
    rows_imported = Column(Integer, nullable=True)
    celery_task_id = Column(String(100), nullable=True)

    # Relationship
    etl_job = relationship("EtlJob", back_populates="logs")

    def __repr__(self) -> str:
        return (
            f"<EtlJobLog id={self.id} job_id={self.etl_job_id} state={self.state!r}>"
        )
