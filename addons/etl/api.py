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
ETL Job REST API

Endpoints
---------
GET    /api/v1/etl/                  – list jobs
POST   /api/v1/etl/                  – create job
GET    /api/v1/etl/{id}              – get job
PUT    /api/v1/etl/{id}              – update job
DELETE /api/v1/etl/{id}              – delete job
POST   /api/v1/etl/{id}/execute/     – trigger immediate execution
GET    /api/v1/etl/{id}/logs/        – execution log history
"""
from __future__ import annotations

import logging
from typing import Any

from flask import g, request, Response
from flask_appbuilder.api import expose, protect, safe
from flask_appbuilder.hooks import before_request
from flask_appbuilder.models.sqla.interface import SQLAInterface
from flask_babel import lazy_gettext as _
from marshmallow import ValidationError

from superset import is_feature_enabled
from superset.constants import MODEL_API_RW_METHOD_PERMISSION_MAP, RouteMethod
from superset.views.base_api import BaseSupersetModelRestApi, statsd_metrics

from addons.etl.commands.create import CreateEtlJobCommand
from addons.etl.commands.delete import DeleteEtlJobCommand
from addons.etl.commands.exceptions import (
    EtlJobCreateFailedError,
    EtlJobDatabaseNotFoundError,
    EtlJobDeleteFailedError,
    EtlJobExecuteFailedError,
    EtlJobInvalidCrontabError,
    EtlJobNameAlreadyExistsError,
    EtlJobNotFoundError,
    EtlJobUpdateFailedError,
    EtlJobUrlNotAllowedError,
)
from addons.etl.commands.update import UpdateEtlJobCommand
from addons.etl.daos.etl import EtlJobDAO, EtlJobLogDAO
from addons.etl.models import EtlJob
from addons.etl.schemas import (
    EtlJobLogSchema,
    EtlJobPostSchema,
    EtlJobPutSchema,
    EtlJobResponseSchema,
)

logger = logging.getLogger(__name__)

etl_job_post_schema = EtlJobPostSchema()
etl_job_put_schema = EtlJobPutSchema()
etl_job_response_schema = EtlJobResponseSchema()
etl_job_log_schema = EtlJobLogSchema()


class EtlJobRestApi(BaseSupersetModelRestApi):
    datamodel = SQLAInterface(EtlJob)

    @before_request
    def ensure_etl_enabled(self) -> Response | None:
        if not is_feature_enabled("ENABLE_ETL_JOBS"):
            return self.response_404()
        return None

    include_route_methods = RouteMethod.REST_MODEL_VIEW_CRUD_SET | {
        "execute",
        "logs",
    }
    class_permission_name = "EtlJob"
    method_permission_name = MODEL_API_RW_METHOD_PERMISSION_MAP
    resource_name = "etl"
    allow_browser_login = True

    list_columns = [
        "id",
        "name",
        "description",
        "active",
        "schedule_type",
        "crontab",
        "run_at",
        "timezone",
        "database_id",
        "database.database_name",
        "target_schema",
        "target_table",
        "file_type",
        "if_exists",
        "last_run_dttm",
        "last_run_state",
        "changed_on",
        "created_on",
    ]
    show_columns = [
        "id",
        "uuid",
        "name",
        "description",
        "active",
        "schedule_type",
        "crontab",
        "run_at",
        "timezone",
        "database_id",
        "database.database_name",
        "database.id",
        "target_schema",
        "target_table",
        "file_type",
        "if_exists",
        "dataframe_index",
        "columns_read",
        "column_data_types",
        "column_rename",
        "http_headers",
        "log_retention",
        "working_timeout",
        "last_run_dttm",
        "last_run_state",
        "sources.id",
        "sources.url",
        "sources.order",
        "sources.sheet_name",
        "sources.delimiter",
        "sources.encoding",
        "changed_on",
        "created_on",
        "changed_by.id",
        "changed_by.first_name",
        "changed_by.last_name",
        "created_by.id",
        "created_by.first_name",
        "created_by.last_name",
    ]
    search_columns = [
        "name",
        "active",
        "schedule_type",
        "last_run_state",
        "database_id",
    ]
    order_columns = [
        "name",
        "active",
        "last_run_dttm",
        "changed_on",
    ]

    # -----------------------------------------------------------------------
    # Custom endpoints
    # -----------------------------------------------------------------------

    @expose("/<int:pk>/execute/", methods=("POST",))
    @protect()
    @safe
    @statsd_metrics
    def execute(self, pk: int) -> Response:
        """
        Trigger an immediate one-off execution of the ETL job.

        ---
        post:
          summary: Execute ETL job immediately
          parameters:
            - in: path
              name: pk
              schema:
                type: integer
          responses:
            200:
              description: Execution accepted; returns the log entry
            404:
              $ref: '#/components/responses/404'
            500:
              $ref: '#/components/responses/500'
        """
        job = EtlJobDAO.find_by_id(pk)
        if not job:
            return self.response_404()

        from addons.etl.tasks.scheduler import execute as celery_execute

        async_result = celery_execute.apply_async(
            kwargs={"job_id": pk},
            time_limit=job.working_timeout + 60,
            soft_time_limit=job.working_timeout,
        )
        return self.response(
            200,
            message=_("ETL job queued for execution"),
            celery_task_id=async_result.id,
        )

    @expose("/<int:pk>/logs/", methods=("GET",))
    @protect()
    @safe
    @statsd_metrics
    def logs(self, pk: int) -> Response:
        """
        Return paginated execution logs for an ETL job.

        ---
        get:
          summary: List ETL job execution logs
          parameters:
            - in: path
              name: pk
              schema:
                type: integer
            - in: query
              name: page
              schema:
                type: integer
                default: 0
            - in: query
              name: page_size
              schema:
                type: integer
                default: 50
          responses:
            200:
              description: List of log entries
            404:
              $ref: '#/components/responses/404'
        """
        job = EtlJobDAO.find_by_id(pk)
        if not job:
            return self.response_404()

        page = request.args.get("page", 0, type=int)
        page_size = request.args.get("page_size", 50, type=int)
        page_size = min(page_size, 200)

        logs, total = EtlJobLogDAO.find_by_job(pk, page=page, page_size=page_size)
        return self.response(
            200,
            count=total,
            result=[etl_job_log_schema.dump(log) for log in logs],
        )

    # -----------------------------------------------------------------------
    # Override CRUD to use Command pattern
    # -----------------------------------------------------------------------

    @expose("/", methods=("POST",))
    @protect()
    @safe
    @statsd_metrics
    def post(self) -> Response:
        """
        Create a new ETL job.

        ---
        post:
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/EtlJobPostSchema'
          responses:
            201:
              description: ETL job created
            400:
              $ref: '#/components/responses/400'
            422:
              $ref: '#/components/responses/422'
        """
        if not request.is_json:
            return self.response_400(message="Request is not JSON")
        try:
            item = etl_job_post_schema.load(request.json)
        except ValidationError as err:
            return self.response_400(message=str(err.messages))

        try:
            job = CreateEtlJobCommand(item).run()
        except EtlJobNameAlreadyExistsError:
            return self.response_422(message=_("An ETL job with this name already exists"))
        except EtlJobDatabaseNotFoundError:
            return self.response_422(message=_("Target database not found"))
        except EtlJobInvalidCrontabError:
            return self.response_422(message=_("Invalid cron expression"))
        except EtlJobUrlNotAllowedError as ex:
            return self.response_400(message=str(ex))
        except EtlJobCreateFailedError:
            return self.response_422(message=_("Failed to create ETL job"))

        return self.response(201, id=job.id, result=etl_job_response_schema.dump(job))

    @expose("/<int:pk>", methods=("PUT",))
    @protect()
    @safe
    @statsd_metrics
    def put(self, pk: int) -> Response:
        """
        Update an existing ETL job.

        ---
        put:
          parameters:
            - in: path
              name: pk
              schema:
                type: integer
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  $ref: '#/components/schemas/EtlJobPutSchema'
          responses:
            200:
              description: ETL job updated
            404:
              $ref: '#/components/responses/404'
            422:
              $ref: '#/components/responses/422'
        """
        if not request.is_json:
            return self.response_400(message="Request is not JSON")
        try:
            item = etl_job_put_schema.load(request.json)
        except ValidationError as err:
            return self.response_400(message=str(err.messages))

        try:
            job = UpdateEtlJobCommand(pk, item).run()
        except EtlJobNotFoundError:
            return self.response_404()
        except EtlJobDatabaseNotFoundError:
            return self.response_422(message=_("Target database not found"))
        except EtlJobInvalidCrontabError:
            return self.response_422(message=_("Invalid cron expression"))
        except EtlJobUrlNotAllowedError as ex:
            return self.response_400(message=str(ex))
        except EtlJobUpdateFailedError:
            return self.response_422(message=_("Failed to update ETL job"))

        return self.response(200, id=job.id, result=etl_job_response_schema.dump(job))

    @expose("/<int:pk>", methods=("DELETE",))
    @protect()
    @safe
    @statsd_metrics
    def delete(self, pk: int) -> Response:
        """
        Delete an ETL job.

        ---
        delete:
          parameters:
            - in: path
              name: pk
              schema:
                type: integer
          responses:
            200:
              description: ETL job deleted
            404:
              $ref: '#/components/responses/404'
        """
        try:
            DeleteEtlJobCommand(pk).run()
        except EtlJobNotFoundError:
            return self.response_404()
        except EtlJobDeleteFailedError:
            return self.response_422(message=_("Failed to delete ETL job"))

        return self.response(200, message="OK")
