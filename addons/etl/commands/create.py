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

import logging
from typing import Any

from croniter import CroniterBadCronError, croniter
from flask_babel import lazy_gettext as _

from superset.commands.base import BaseCommand, CreateMixin
from superset.daos.database import DatabaseDAO

from addons.etl.commands.exceptions import (
    EtlJobCreateFailedError,
    EtlJobDatabaseNotFoundError,
    EtlJobInvalidCrontabError,
    EtlJobNameAlreadyExistsError,
    EtlJobUrlNotAllowedError,
)
from addons.etl.daos.etl import EtlJobDAO
from addons.etl.models import EtlJob, EtlScheduleType
from addons.etl.utils import validate_source_urls

logger = logging.getLogger(__name__)


class CreateEtlJobCommand(CreateMixin, BaseCommand):
    def __init__(self, properties: dict[str, Any]) -> None:
        self._properties = properties.copy()

    def run(self) -> EtlJob:
        self.validate()
        try:
            return EtlJobDAO.create(self._properties)
        except Exception as ex:
            logger.exception("Failed to create ETL job")
            raise EtlJobCreateFailedError() from ex

    def validate(self) -> None:
        # Check name uniqueness
        existing = (
            EtlJobDAO.find_all()
        )  # lightweight check; name has a unique constraint anyway
        for job in existing:
            if job.name == self._properties.get("name"):
                raise EtlJobNameAlreadyExistsError()

        # Check target database exists
        db_id = self._properties.get("database_id")
        if not db_id or not DatabaseDAO.find_by_id(db_id):
            raise EtlJobDatabaseNotFoundError()

        # Validate crontab expression when schedule_type is cron
        sched_type = self._properties.get("schedule_type", EtlScheduleType.CRON)
        if sched_type == EtlScheduleType.CRON:
            crontab = self._properties.get("crontab", "")
            if not crontab or not croniter.is_valid(crontab):
                raise EtlJobInvalidCrontabError()

        # Validate source URLs (SSRF protection)
        sources = self._properties.get("sources", [])
        urls = [s["url"] for s in sources if "url" in s]
        if urls:
            try:
                validate_source_urls(urls)
            except ValueError as ex:
                raise EtlJobUrlNotAllowedError() from ex
