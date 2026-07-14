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
Unit tests for Create / Update / Delete ETL job commands.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from addons.etl.commands.exceptions import (
    EtlJobCreateFailedError,
    EtlJobDatabaseNotFoundError,
    EtlJobDeleteFailedError,
    EtlJobInvalidCrontabError,
    EtlJobNameAlreadyExistsError,
    EtlJobNotFoundError,
    EtlJobUpdateFailedError,
    EtlJobUrlNotAllowedError,
)
from tests.unit_tests.addons.etl.conftest import make_job_props, make_source_props


# ===========================================================================
# CreateEtlJobCommand
# ===========================================================================


@patch("addons.etl.commands.create.validate_source_urls")
@patch("addons.etl.commands.create.DatabaseDAO.find_by_id")
@patch("addons.etl.commands.create.EtlJobDAO.find_all", return_value=[])
@patch("addons.etl.commands.create.EtlJobDAO.create")
def test_create_succeeds(
    mock_create: MagicMock,
    mock_find_all: MagicMock,
    mock_db_find: MagicMock,
    mock_validate_urls: MagicMock,
) -> None:
    from addons.etl.commands.create import CreateEtlJobCommand
    from addons.etl.models import EtlJob

    mock_db_find.return_value = MagicMock()  # database exists
    mock_create.return_value = MagicMock(spec=EtlJob)

    cmd = CreateEtlJobCommand(make_job_props())
    result = cmd.run()

    mock_create.assert_called_once()
    assert result is not None


@patch("addons.etl.commands.create.DatabaseDAO.find_by_id")
@patch("addons.etl.commands.create.EtlJobDAO.find_all")
def test_create_raises_when_name_exists(
    mock_find_all: MagicMock,
    mock_db_find: MagicMock,
) -> None:
    from addons.etl.commands.create import CreateEtlJobCommand
    from addons.etl.models import EtlJob

    existing = MagicMock(spec=EtlJob)
    existing.name = "test_etl_job"
    mock_find_all.return_value = [existing]

    with pytest.raises(EtlJobNameAlreadyExistsError):
        CreateEtlJobCommand(make_job_props(name="test_etl_job")).run()


@patch("addons.etl.commands.create.DatabaseDAO.find_by_id", return_value=None)
@patch("addons.etl.commands.create.EtlJobDAO.find_all", return_value=[])
def test_create_raises_when_database_not_found(
    mock_find_all: MagicMock,
    mock_db_find: MagicMock,
) -> None:
    from addons.etl.commands.create import CreateEtlJobCommand

    with pytest.raises(EtlJobDatabaseNotFoundError):
        CreateEtlJobCommand(make_job_props(database_id=999)).run()


@patch("addons.etl.commands.create.DatabaseDAO.find_by_id")
@patch("addons.etl.commands.create.EtlJobDAO.find_all", return_value=[])
def test_create_raises_on_invalid_crontab(
    mock_find_all: MagicMock,
    mock_db_find: MagicMock,
) -> None:
    from addons.etl.commands.create import CreateEtlJobCommand
    from addons.etl.models import EtlScheduleType

    mock_db_find.return_value = MagicMock()

    with pytest.raises(EtlJobInvalidCrontabError):
        CreateEtlJobCommand(
            make_job_props(
                schedule_type=EtlScheduleType.CRON,
                crontab="not_a_cron",
            )
        ).run()


@patch("addons.etl.commands.create.validate_source_urls")
@patch("addons.etl.commands.create.DatabaseDAO.find_by_id")
@patch("addons.etl.commands.create.EtlJobDAO.find_all", return_value=[])
def test_create_raises_on_disallowed_url(
    mock_find_all: MagicMock,
    mock_db_find: MagicMock,
    mock_validate: MagicMock,
) -> None:
    from addons.etl.commands.create import CreateEtlJobCommand

    mock_db_find.return_value = MagicMock()
    mock_validate.side_effect = ValueError("URL scheme not allowed")

    with pytest.raises(EtlJobUrlNotAllowedError):
        CreateEtlJobCommand(
            make_job_props(
                sources=[make_source_props(url="ftp://bad.com/data.csv")]
            )
        ).run()


# ===========================================================================
# UpdateEtlJobCommand
# ===========================================================================


@patch("addons.etl.commands.update.validate_source_urls")
@patch("addons.etl.commands.update.DatabaseDAO.find_by_id")
@patch("addons.etl.commands.update.EtlJobDAO.find_by_id")
@patch("addons.etl.commands.update.EtlJobDAO.update")
def test_update_succeeds(
    mock_update: MagicMock,
    mock_find: MagicMock,
    mock_db_find: MagicMock,
    mock_validate: MagicMock,
) -> None:
    from addons.etl.commands.update import UpdateEtlJobCommand
    from addons.etl.models import EtlJob

    mock_find.return_value = MagicMock(spec=EtlJob)
    mock_db_find.return_value = MagicMock()
    mock_update.return_value = MagicMock(spec=EtlJob)

    result = UpdateEtlJobCommand(1, {"name": "updated_name"}).run()
    mock_update.assert_called_once()


@patch("addons.etl.commands.update.EtlJobDAO.find_by_id", return_value=None)
def test_update_raises_when_job_not_found(mock_find: MagicMock) -> None:
    from addons.etl.commands.update import UpdateEtlJobCommand

    with pytest.raises(EtlJobNotFoundError):
        UpdateEtlJobCommand(999, {"name": "x"}).run()


@patch("addons.etl.commands.update.EtlJobDAO.find_by_id")
def test_update_raises_on_invalid_crontab(mock_find: MagicMock) -> None:
    from addons.etl.commands.update import UpdateEtlJobCommand
    from addons.etl.models import EtlJob, EtlScheduleType

    job = MagicMock(spec=EtlJob)
    job.schedule_type = EtlScheduleType.CRON
    job.crontab = "0 * * * *"
    mock_find.return_value = job

    with pytest.raises(EtlJobInvalidCrontabError):
        UpdateEtlJobCommand(
            1, {"schedule_type": EtlScheduleType.CRON, "crontab": "bad_cron"}
        ).run()


# ===========================================================================
# DeleteEtlJobCommand
# ===========================================================================


@patch("addons.etl.commands.delete.EtlJobDAO.delete")
@patch("addons.etl.commands.delete.EtlJobDAO.find_by_id")
def test_delete_succeeds(
    mock_find: MagicMock,
    mock_delete: MagicMock,
) -> None:
    from addons.etl.commands.delete import DeleteEtlJobCommand
    from addons.etl.models import EtlJob

    mock_find.return_value = MagicMock(spec=EtlJob)

    DeleteEtlJobCommand(1).run()
    mock_delete.assert_called_once()


@patch("addons.etl.commands.delete.EtlJobDAO.find_by_id", return_value=None)
def test_delete_raises_when_job_not_found(mock_find: MagicMock) -> None:
    from addons.etl.commands.delete import DeleteEtlJobCommand

    with pytest.raises(EtlJobNotFoundError):
        DeleteEtlJobCommand(999).run()


@patch("addons.etl.commands.delete.EtlJobDAO.find_by_id")
@patch("addons.etl.commands.delete.EtlJobDAO.delete", side_effect=Exception("DB error"))
def test_delete_raises_delete_failed_on_db_error(
    mock_delete: MagicMock,
    mock_find: MagicMock,
) -> None:
    from addons.etl.commands.delete import DeleteEtlJobCommand
    from addons.etl.models import EtlJob

    mock_find.return_value = MagicMock(spec=EtlJob)

    with pytest.raises(EtlJobDeleteFailedError):
        DeleteEtlJobCommand(1).run()
