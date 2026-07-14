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

from croniter import croniter

from superset.commands.base import BaseCommand, UpdateMixin
from superset.daos.database import DatabaseDAO

from addons.etl.commands.exceptions import (
    EtlJobDatabaseNotFoundError,
    EtlJobInvalidCrontabError,
    EtlJobNotFoundError,
    EtlJobUpdateFailedError,
    EtlJobUrlNotAllowedError,
)
from addons.etl.daos.etl import EtlJobDAO
from addons.etl.models import EtlJob, EtlScheduleType
from addons.etl.utils import validate_source_urls

logger = logging.getLogger(__name__)


class UpdateEtlJobCommand(UpdateMixin, BaseCommand):
    def __init__(self, job_id: int, properties: dict[str, Any]) -> None:
        self._job_id = job_id
        self._properties = properties.copy()
        self._job: EtlJob | None = None

    def run(self) -> EtlJob:
        self.validate()
        assert self._job is not None
        try:
            return EtlJobDAO.update(self._job, self._properties)
        except Exception as ex:
            logger.exception("Failed to update ETL job %s", self._job_id)
            raise EtlJobUpdateFailedError() from ex

    def validate(self) -> None:
        self._job = EtlJobDAO.find_by_id(self._job_id)
        if not self._job:
            raise EtlJobNotFoundError()

        # Validate database if changing
        if "database_id" in self._properties:
            db_id = self._properties["database_id"]
            if not db_id or not DatabaseDAO.find_by_id(db_id):
                raise EtlJobDatabaseNotFoundError()

        # Validate crontab if changing schedule
        sched_type = self._properties.get("schedule_type", self._job.schedule_type)
        crontab = self._properties.get("crontab", self._job.crontab)
        if sched_type == EtlScheduleType.CRON:
            if not crontab or not croniter.is_valid(crontab):
                raise EtlJobInvalidCrontabError()

        # Validate URLs if sources are changing
        sources = self._properties.get("sources")
        if sources is not None:
            urls = [s["url"] for s in sources if "url" in s]
            if urls:
                try:
                    validate_source_urls(urls)
                except ValueError as ex:
                    raise EtlJobUrlNotAllowedError() from ex
