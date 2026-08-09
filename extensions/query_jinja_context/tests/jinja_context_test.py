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
# pylint: disable=invalid-name, unused-argument
from __future__ import annotations

from typing import Any

import pytest
from pytest_mock import MockerFixture

from superset.commands.dataset.exceptions import DatasetNotFoundError
from superset.connectors.sqla.models import (
    SqlaTable,
    TableColumn,
)
from superset.jinja_context import (
    get_template_processor,
    result_from_macro,
)
from superset.models.core import Database



# ---------------------------------------------------------------------------
# result_from_macro tests
# ---------------------------------------------------------------------------


def _make_physical_dataset(mocker: MockerFixture) -> SqlaTable:
    """Return a mock physical SqlaTable for result_from tests."""
    db = Database(database_name="db_a", sqlalchemy_uri="sqlite://")
    ds = SqlaTable(
        table_name="my_table",
        schema="my_schema",
        sql=None,
        database=db,
        columns=[TableColumn(column_name="region", type="VARCHAR")],
        metrics=[],
    )
    DatasetDAO = mocker.patch("superset.daos.dataset.DatasetDAO")  # noqa: N806
    DatasetDAO.find_by_id.return_value = ds
    mocker.patch(
        "superset.jinja_context.security_manager.raise_for_access",
        return_value=None,
    )
    return ds


def test_result_from_macro_not_found(mocker: MockerFixture) -> None:
    """result_from_macro raises DatasetNotFoundError when dataset is missing."""
    DatasetDAO = mocker.patch("superset.daos.dataset.DatasetDAO")  # noqa: N806
    DatasetDAO.find_by_id.return_value = None

    with pytest.raises(DatasetNotFoundError):
        result_from_macro("SELECT 1 FROM dataset", 99)


def test_result_from_macro_physical_table(mocker: MockerFixture) -> None:
    """Physical dataset — ``dataset`` is replaced with quoted schema.table."""
    ds = _make_physical_dataset(mocker)

    # Capture the SQL that is actually executed.
    executed: list[str] = []

    class FakeResult:
        def fetchmany(self, n: int) -> list[tuple[Any, ...]]:
            return [("US",), ("EU",)]

    class FakeConn:
        def execute(self, stmt: Any) -> FakeResult:
            executed.append(str(stmt))
            return FakeResult()

        def __enter__(self) -> "FakeConn":
            return self

        def __exit__(self, *_: Any) -> None:
            pass

    class FakeEngine:
        def connect(self) -> FakeConn:
            return FakeConn()

        def __enter__(self) -> "FakeEngine":
            return self

        def __exit__(self, *_: Any) -> None:
            pass

    mocker.patch.object(ds.database, "get_sqla_engine", return_value=FakeEngine())

    result = result_from_macro(
        "SELECT region FROM dataset WHERE active = 1", ds.id or 1
    )

    assert result == ["US", "EU"]
    # The keyword `dataset` must have been replaced by the quoted table name.
    assert "dataset" not in executed[0]
    assert "my_table" in executed[0]


def test_result_from_macro_virtual_dataset(mocker: MockerFixture) -> None:
    """Virtual (SQL-based) dataset — ``dataset`` is replaced with a subquery."""
    db = Database(database_name="db_b", sqlalchemy_uri="sqlite://")
    ds = SqlaTable(
        table_name="virtual_ds",
        schema=None,
        sql="SELECT id, region FROM raw_table",
        database=db,
        columns=[TableColumn(column_name="region", type="VARCHAR")],
        metrics=[],
    )
    DatasetDAO = mocker.patch("superset.daos.dataset.DatasetDAO")  # noqa: N806
    DatasetDAO.find_by_id.return_value = ds
    mocker.patch(
        "superset.jinja_context.security_manager.raise_for_access",
        return_value=None,
    )

    executed: list[str] = []

    class FakeResult:
        def fetchmany(self, n: int) -> list[tuple[Any, ...]]:
            return [("APAC",)]

    class FakeConn:
        def execute(self, stmt: Any) -> FakeResult:
            executed.append(str(stmt))
            return FakeResult()

        def __enter__(self) -> "FakeConn":
            return self

        def __exit__(self, *_: Any) -> None:
            pass

    class FakeEngine:
        def connect(self) -> FakeConn:
            return FakeConn()

        def __enter__(self) -> "FakeEngine":
            return self

        def __exit__(self, *_: Any) -> None:
            pass

    mocker.patch.object(ds.database, "get_sqla_engine", return_value=FakeEngine())

    result = result_from_macro("SELECT region FROM dataset", ds.id or 2)

    assert result == ["APAC"]
    # The subquery must embed the virtual dataset's SQL.
    assert "raw_table" in executed[0]


def test_result_from_macro_named_col(mocker: MockerFixture) -> None:
    """col parameter accepts a column name string."""
    ds = _make_physical_dataset(mocker)

    class FakeRow:
        _mapping = {"region": "NA"}

    class FakeResult:
        def fetchmany(self, n: int) -> list[Any]:
            return [FakeRow()]

    class FakeConn:
        def execute(self, stmt: Any) -> FakeResult:
            return FakeResult()

        def __enter__(self) -> "FakeConn":
            return self

        def __exit__(self, *_: Any) -> None:
            pass

    class FakeEngine:
        def connect(self) -> FakeConn:
            return FakeConn()

        def __enter__(self) -> "FakeEngine":
            return self

        def __exit__(self, *_: Any) -> None:
            pass

    mocker.patch.object(ds.database, "get_sqla_engine", return_value=FakeEngine())

    result = result_from_macro(
        "SELECT region FROM dataset", ds.id or 1, col="region"
    )
    assert result == ["NA"]


def test_result_from_macro_max_rows(mocker: MockerFixture) -> None:
    """max_rows is forwarded to fetchmany."""
    ds = _make_physical_dataset(mocker)

    fetched_sizes: list[int] = []

    class FakeResult:
        def fetchmany(self, n: int) -> list[tuple[Any, ...]]:
            fetched_sizes.append(n)
            return []

    class FakeConn:
        def execute(self, stmt: Any) -> FakeResult:
            return FakeResult()

        def __enter__(self) -> "FakeConn":
            return self

        def __exit__(self, *_: Any) -> None:
            pass

    class FakeEngine:
        def connect(self) -> FakeConn:
            return FakeConn()

        def __enter__(self) -> "FakeEngine":
            return self

        def __exit__(self, *_: Any) -> None:
            pass

    mocker.patch.object(ds.database, "get_sqla_engine", return_value=FakeEngine())

    result_from_macro("SELECT region FROM dataset", ds.id or 1, max_rows=5)
    assert fetched_sizes == [5]


def test_result_from_registered_in_jinja_context(mocker: MockerFixture) -> None:
    """result_from is available as a Jinja template function."""
    database = Database(database_name="my_db", sqlalchemy_uri="sqlite://")
    processor = get_template_processor(database=database)
    assert "result_from" in processor._context
