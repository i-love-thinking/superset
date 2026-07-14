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

from superset.commands.base import BaseCommand

from addons.etl.commands.exceptions import (
    EtlJobDeleteFailedError,
    EtlJobNotFoundError,
)
from addons.etl.daos.etl import EtlJobDAO
from addons.etl.models import EtlJob

logger = logging.getLogger(__name__)


class DeleteEtlJobCommand(BaseCommand):
    def __init__(self, job_id: int) -> None:
        self._job_id = job_id
        self._job: EtlJob | None = None

    def run(self) -> None:
        self.validate()
        assert self._job is not None
        try:
            EtlJobDAO.delete(self._job)
        except Exception as ex:
            logger.exception("Failed to delete ETL job %s", self._job_id)
            raise EtlJobDeleteFailedError() from ex

    def validate(self) -> None:
        self._job = EtlJobDAO.find_by_id(self._job_id)
        if not self._job:
            raise EtlJobNotFoundError()
