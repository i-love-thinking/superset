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
"""ETL addon: create etl_jobs, etl_job_sources, etl_job_logs tables

Revision ID: b1e2f3a4c5d6
Revises: a7d3f1b9c2e4
Create Date: 2026-07-15 00-00-00.000000

"""

# revision identifiers, used by Alembic.
revision = "b1e2f3a4c5d6"
down_revision = "a7d3f1b9c2e4"

import sqlalchemy as sa
from alembic import op
from sqlalchemy_utils import UUIDType


def upgrade() -> None:
    # ── etl_jobs ──────────────────────────────────────────────────────
    op.create_table(
        "etl_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uuid", UUIDType(binary=True), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        # Schedule
        sa.Column("schedule_type", sa.String(50), nullable=False, server_default="cron"),
        sa.Column("crontab", sa.String(1000), nullable=True),
        sa.Column("run_at", sa.DateTime(), nullable=True),
        sa.Column("timezone", sa.String(100), nullable=False, server_default="UTC"),
        # Target
        sa.Column("database_id", sa.Integer(), nullable=False),
        sa.Column("target_schema", sa.String(250), nullable=True),
        sa.Column("target_table", sa.String(250), nullable=False),
        # File options
        sa.Column("file_type", sa.String(50), nullable=False, server_default="auto"),
        sa.Column("if_exists", sa.String(50), nullable=False, server_default="fail"),
        sa.Column("dataframe_index", sa.Boolean(), nullable=False, server_default=sa.false()),
        # Column processing
        sa.Column("columns_read", sa.Text(), nullable=True),
        sa.Column("column_data_types", sa.Text(), nullable=True),
        sa.Column("column_rename", sa.Text(), nullable=True),
        # HTTP options
        sa.Column("http_headers", sa.Text(), nullable=True),
        # Status
        sa.Column("last_run_dttm", sa.DateTime(), nullable=True),
        sa.Column("last_run_state", sa.String(50), nullable=True),
        # Operational
        sa.Column("log_retention", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("working_timeout", sa.Integer(), nullable=False, server_default="3600"),
        # Audit
        sa.Column("created_on", sa.DateTime(), nullable=True),
        sa.Column("changed_on", sa.DateTime(), nullable=True),
        sa.Column("created_by_fk", sa.Integer(), nullable=True),
        sa.Column("changed_by_fk", sa.Integer(), nullable=True),
        # Extra JSON
        sa.Column("extra_json", sa.Text(), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("name"),
        sa.ForeignKeyConstraint(["database_id"], ["dbs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_fk"], ["ab_user.id"]),
        sa.ForeignKeyConstraint(["changed_by_fk"], ["ab_user.id"]),
    )
    op.create_index("ix_etl_jobs_active", "etl_jobs", ["active"])
    op.create_index("ix_etl_jobs_last_run_state", "etl_jobs", ["last_run_state"])

    # ── etl_job_sources ───────────────────────────────────────────────
    op.create_table(
        "etl_job_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("etl_job_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sheet_name", sa.String(250), nullable=True),
        sa.Column("delimiter", sa.String(10), nullable=True),
        sa.Column("encoding", sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["etl_job_id"], ["etl_jobs.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_etl_job_sources_etl_job_id", "etl_job_sources", ["etl_job_id"]
    )

    # ── etl_job_logs ──────────────────────────────────────────────────
    op.create_table(
        "etl_job_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("etl_job_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_dttm", sa.DateTime(), nullable=True),
        sa.Column("start_dttm", sa.DateTime(), nullable=False),
        sa.Column("end_dttm", sa.DateTime(), nullable=True),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("rows_imported", sa.Integer(), nullable=True),
        sa.Column("celery_task_id", sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["etl_job_id"], ["etl_jobs.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_etl_job_logs_etl_job_id", "etl_job_logs", ["etl_job_id"])
    op.create_index("ix_etl_job_logs_state", "etl_job_logs", ["state"])
    op.create_index("ix_etl_job_logs_start_dttm", "etl_job_logs", ["start_dttm"])


def downgrade() -> None:
    op.drop_table("etl_job_logs")
    op.drop_table("etl_job_sources")
    op.drop_table("etl_jobs")
