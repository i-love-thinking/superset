
import re
from typing import Any

from sqlalchemy import text as sa_text

from superset import security_manager
from superset.commands.dataset.exceptions import DatasetNotFoundError
from superset.daos.dataset import DatasetDAO


def result_from_macro(
    sql_string: str,
    dataset_id: int,
    col: int | str = 0,
    max_rows: int = 1000,
) -> list[Any]:
    """
    Execute ``sql_string`` against the given dataset's own database connection and
    return a flat list of values decoupled from the current query's database.

    ``dataset`` is a reserved placeholder in ``sql_string`` that is replaced before
    execution:

    * **Physical datasets** — replaced with the dialect-quoted, schema-qualified
      table name (e.g. ``"analytics"."dim_regions"``).
    * **Virtual (SQL-based) datasets** — replaced with the dataset's defining SQL
      wrapped as an aliased subquery (e.g. ``(SELECT … FROM …) AS dataset_42``).

    The query is executed on the dataset's own ``Database`` connection so it works
    even when the calling query targets a different database engine (cross-DB use).

    :param sql_string: SQL to execute.  Use the bare word ``dataset`` wherever the
        table reference should appear, e.g.
        ``"SELECT region FROM dataset WHERE active = 1"``.
    :param dataset_id: ID of the dataset to query.
    :param col: Column to extract from each returned row — either a 0-based integer
        index or a column-name string.  Defaults to ``0`` (first column).
    :param max_rows: Maximum number of rows fetched from the database (safety cap).
        Defaults to ``1000``.
    :returns: A flat list of primitive values from the specified column.

    Usage examples::

        -- scalar lookup
        WHERE category = '{{ result_from("SELECT name FROM dataset LIMIT 1", 7)[0] }}'

        -- list membership via where_in filter
        WHERE region IN (
          {{ result_from("SELECT region FROM dataset WHERE active = 1", 42)
             | where_in }}
        )

        -- named column extraction
        WHERE id IN (
          {{ result_from("SELECT user_id FROM dataset", 5, col="user_id") | where_in }}
        )
    """


    dataset = DatasetDAO.find_by_id(dataset_id)
    if not dataset:
        raise DatasetNotFoundError(f"Dataset {dataset_id} not found!")

    security_manager.raise_for_access(datasource=dataset)

    db = dataset.database

    if dataset.is_virtual:
        # Virtual (SQL-defined) dataset — wrap its SQL as an aliased subquery.
        dataset_ref = f"(\n{dataset.sql}\n) AS dataset_{dataset_id}"
    else:
        # Physical table — quote identifiers via the target dialect.
        dialect = db.get_dialect()
        preparer = dialect.identifier_preparer
        quoted_table = preparer.quote(dataset.table_name)
        if dataset.schema:
            quoted_schema = preparer.quote(dataset.schema)
            dataset_ref = f"{quoted_schema}.{quoted_table}"
        else:
            dataset_ref = quoted_table

    substituted_sql = re.sub(r"\bdataset\b", dataset_ref, sql_string)

    with db.get_sqla_engine(catalog=dataset.catalog, schema=dataset.schema) as engine:
        with engine.connect() as conn:
            result = conn.execute(sa_text(substituted_sql))
            rows = result.fetchmany(max_rows)

    def _to_primitive(value: Any) -> str | int | float | bool | None:
        """Coerce DB-native types (Decimal, date, …) to JSON-safe primitives."""
        if isinstance(value, (int, float, bool, type(None))):
            return value
        return str(value)

    if isinstance(col, int):
        return [_to_primitive(row[col]) for row in rows]
    return [_to_primitive(row._mapping[col]) for row in rows]

