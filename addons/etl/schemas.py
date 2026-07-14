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

from marshmallow import fields, post_load, Schema, validate, validates, ValidationError
from marshmallow.validate import OneOf

from addons.etl.models import EtlFileType, EtlIfExists, EtlScheduleType


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------


class EtlJobSourceSchema(Schema):
    id = fields.Integer(dump_only=True)
    url = fields.String(
        required=True,
        metadata={"description": "HTTP/HTTPS URL of the remote file"},
    )
    order = fields.Integer(
        load_default=0,
        metadata={"description": "Download order when multiple sources are present"},
    )
    sheet_name = fields.String(
        allow_none=True,
        load_default=None,
        metadata={"description": "Excel sheet name or index (Excel files only)"},
    )
    delimiter = fields.String(
        allow_none=True,
        load_default=None,
        metadata={"description": "Column delimiter for CSV/TSV; defaults to ',' or '\\t'"},
    )
    encoding = fields.String(
        allow_none=True,
        load_default=None,
        metadata={"description": "Force character encoding; null = auto-detect"},
    )

    @validates("url")
    def validate_url(self, value: str) -> None:
        if not value.startswith(("http://", "https://", "smb://")):
            raise ValidationError("URL must start with http://, https://, or smb://")


class EtlJobLogSchema(Schema):
    id = fields.Integer(dump_only=True)
    etl_job_id = fields.Integer(dump_only=True)
    scheduled_dttm = fields.DateTime(dump_only=True, allow_none=True)
    start_dttm = fields.DateTime(dump_only=True)
    end_dttm = fields.DateTime(dump_only=True, allow_none=True)
    state = fields.String(dump_only=True)
    error_message = fields.String(dump_only=True, allow_none=True)
    rows_imported = fields.Integer(dump_only=True, allow_none=True)
    celery_task_id = fields.String(dump_only=True, allow_none=True)


# ---------------------------------------------------------------------------
# Job write schema (POST / PUT)
# ---------------------------------------------------------------------------


class EtlJobPostSchema(Schema):
    name = fields.String(
        required=True,
        validate=validate.Length(min=1, max=150),
        metadata={"description": "Unique human-readable name for this ETL job"},
    )
    description = fields.String(
        allow_none=True,
        load_default=None,
        metadata={"description": "Optional description"},
    )
    active = fields.Boolean(
        load_default=True,
        metadata={"description": "Whether this job should be triggered by the scheduler"},
    )

    # Schedule
    schedule_type = fields.String(
        load_default=EtlScheduleType.CRON,
        validate=OneOf([e.value for e in EtlScheduleType]),
        metadata={"description": "'cron' for recurring schedules; 'onetime' for a single run"},
    )
    crontab = fields.String(
        allow_none=True,
        load_default=None,
        metadata={"description": "Cron expression (required when schedule_type='cron')"},
    )
    run_at = fields.DateTime(
        allow_none=True,
        load_default=None,
        metadata={"description": "ISO-8601 datetime for a one-time execution"},
    )
    timezone = fields.String(
        load_default="UTC",
        validate=validate.Length(max=100),
        metadata={"description": "IANA timezone name, e.g. 'Asia/Taipei'"},
    )

    # Target
    database_id = fields.Integer(
        required=True,
        metadata={"description": "ID of the target Superset database"},
    )
    target_schema = fields.String(
        allow_none=True,
        load_default=None,
        validate=validate.Length(max=250),
        metadata={"description": "Target schema; null uses the database default"},
    )
    target_table = fields.String(
        required=True,
        validate=validate.Length(min=1, max=250),
        metadata={"description": "Target table name"},
    )

    # File options
    file_type = fields.String(
        load_default=EtlFileType.AUTO,
        validate=OneOf([e.value for e in EtlFileType]),
        metadata={"description": "File type: auto / csv / tsv / excel"},
    )
    if_exists = fields.String(
        load_default=EtlIfExists.FAIL,
        validate=OneOf([e.value for e in EtlIfExists]),
        metadata={"description": "Behaviour when the target table already exists"},
    )
    dataframe_index = fields.Boolean(
        load_default=False,
        metadata={"description": "Write DataFrame row index into the table"},
    )

    # Column processing
    columns_read = fields.String(
        allow_none=True,
        load_default=None,
        metadata={
            "description": (
                "JSON-encoded list of column names to keep, "
                'e.g. \'["col_a", "col_b"]\'. Null keeps all columns.'
            )
        },
    )
    column_data_types = fields.String(
        allow_none=True,
        load_default=None,
        metadata={
            "description": (
                "JSON-encoded dict mapping column names to pandas dtype strings, "
                'e.g. \'{"amount": "float64", "category": "string"}\''
            )
        },
    )
    column_rename = fields.String(
        allow_none=True,
        load_default=None,
        metadata={
            "description": (
                "JSON-encoded dict mapping original column names to new names, "
                'e.g. \'{"old_name": "new_name"}\''
            )
        },
    )

    # HTTP options
    http_headers = fields.String(
        allow_none=True,
        load_default=None,
        metadata={
            "description": (
                "JSON-encoded dict of HTTP request headers, "
                'e.g. \'{"Authorization": "Bearer token123"}\''
            )
        },
    )

    # Operational
    log_retention = fields.Integer(
        load_default=90,
        validate=validate.Range(min=1),
        metadata={"description": "Number of days to retain execution logs"},
    )
    working_timeout = fields.Integer(
        load_default=3600,
        validate=validate.Range(min=60),
        metadata={"description": "Celery task soft-time-limit in seconds"},
    )

    # Sources
    sources = fields.List(
        fields.Nested(EtlJobSourceSchema),
        required=True,
        validate=validate.Length(min=1),
        metadata={"description": "One or more source URL configurations"},
    )


class EtlJobPutSchema(EtlJobPostSchema):
    """Same as Post but all top-level fields are optional."""

    name = fields.String(
        validate=validate.Length(min=1, max=150),
        metadata={"description": "Unique human-readable name for this ETL job"},
    )
    database_id = fields.Integer(
        metadata={"description": "ID of the target Superset database"},
    )
    target_table = fields.String(
        validate=validate.Length(min=1, max=250),
        metadata={"description": "Target table name"},
    )
    sources = fields.List(
        fields.Nested(EtlJobSourceSchema),
        validate=validate.Length(min=1),
        metadata={"description": "One or more source URL configurations"},
    )


# ---------------------------------------------------------------------------
# Job read schema
# ---------------------------------------------------------------------------


class EtlJobResponseSchema(Schema):
    id = fields.Integer(dump_only=True)
    uuid = fields.String(dump_only=True)
    name = fields.String(dump_only=True)
    description = fields.String(dump_only=True, allow_none=True)
    active = fields.Boolean(dump_only=True)

    schedule_type = fields.String(dump_only=True)
    crontab = fields.String(dump_only=True, allow_none=True)
    run_at = fields.DateTime(dump_only=True, allow_none=True)
    timezone = fields.String(dump_only=True)

    database_id = fields.Integer(dump_only=True)
    database = fields.Nested(
        lambda: _DatabaseSummarySchema(),
        dump_only=True,
        allow_none=True,
    )
    target_schema = fields.String(dump_only=True, allow_none=True)
    target_table = fields.String(dump_only=True)

    file_type = fields.String(dump_only=True)
    if_exists = fields.String(dump_only=True)
    dataframe_index = fields.Boolean(dump_only=True)

    columns_read = fields.String(dump_only=True, allow_none=True)
    column_data_types = fields.String(dump_only=True, allow_none=True)
    column_rename = fields.String(dump_only=True, allow_none=True)
    http_headers = fields.String(dump_only=True, allow_none=True)

    last_run_dttm = fields.DateTime(dump_only=True, allow_none=True)
    last_run_state = fields.String(dump_only=True, allow_none=True)

    log_retention = fields.Integer(dump_only=True)
    working_timeout = fields.Integer(dump_only=True)

    sources = fields.List(fields.Nested(EtlJobSourceSchema), dump_only=True)

    changed_on = fields.DateTime(dump_only=True)
    created_on = fields.DateTime(dump_only=True)
    changed_by = fields.Nested(lambda: _UserSummarySchema(), dump_only=True, allow_none=True)
    created_by = fields.Nested(lambda: _UserSummarySchema(), dump_only=True, allow_none=True)


class _UserSummarySchema(Schema):
    id = fields.Integer()
    first_name = fields.String()
    last_name = fields.String()


class _DatabaseSummarySchema(Schema):
    id = fields.Integer()
    database_name = fields.String()
