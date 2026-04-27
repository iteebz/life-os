from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from life.core.errors import NotFoundError
from life.core.types import Conn
from life.store.connection import DataclassInstance, from_row


@dataclass(slots=True)
class Query[T: DataclassInstance]:
    _table: str
    _model: type[T] | None = None
    _select: str = "*"
    _conditions: list[str] | None = None
    _params: list[Any] | None = None
    _order: str | None = None
    _limit: int | None = None
    _joins: list[str] | None = None

    def select(self, cols: str) -> Query[T]:
        return replace(self, _select=cols)

    def where(self, condition: str, *params: Any) -> Query[T]:
        return replace(
            self,
            _conditions=[*(self._conditions or []), condition],
            _params=[*(self._params or []), *params],
        )

    def where_if(self, condition: str, value: Any) -> Query[T]:
        return self if value is None else self.where(condition, value)

    def where_in(self, column: str, values: list[Any]) -> Query[T]:
        if not values:
            return self.where("1 = 0")
        return self.where(f"{column} IN ({','.join('?' * len(values))})", *values)

    def join(self, join_clause: str) -> Query[T]:
        return replace(self, _joins=[*(self._joins or []), join_clause])

    def order(self, clause: str) -> Query[T]:
        return replace(self, _order=clause)

    def limit(self, n: int | None) -> Query[T]:
        return replace(self, _limit=n)

    def not_deleted(self) -> Query[T]:
        return self.where("deleted_at IS NULL")

    def build(self) -> tuple[str, list[Any]]:
        parts = [f"SELECT {self._select} FROM {self._table}"]  # noqa: S608
        params = list(self._params or [])
        if self._joins:
            parts.extend(self._joins)
        if self._conditions:
            parts.append("WHERE " + " AND ".join(self._conditions))
        if self._order:
            parts.append(f"ORDER BY {self._order}")
        if self._limit is not None:
            parts.append("LIMIT ?")
            params.append(self._limit)
        return " ".join(parts), params

    def _resolve_model(self, cls: type[T] | None = None) -> type[T]:
        model = cls or self._model
        if model is None:
            raise TypeError("No model bound - pass cls or use query(table, Model)")
        return model

    def execute(self, conn: Conn) -> list[Any]:
        sql, params = self.build()
        return conn.execute(sql, params).fetchall()

    def fetch(self, conn: Conn, cls: type[T] | None = None) -> list[T]:
        model = self._resolve_model(cls)
        return [from_row(row, model) for row in self.execute(conn)]

    def fetch_one(self, conn: Conn, cls: type[T] | None = None) -> T | None:
        model = self._resolve_model(cls)
        rows = self.limit(1).execute(conn)
        return from_row(rows[0], model) if rows else None

    def get(self, conn: Conn, id: str, cls: type[T] | None = None) -> T:
        model = self._resolve_model(cls)
        row = self.where("id = ?", id).limit(1).execute(conn)
        if not row:
            raise NotFoundError(id)
        return from_row(row[0], model)

    def count(self, conn: Conn) -> int:
        q = replace(self, _select="COUNT(*)", _order=None, _limit=None)
        sql, params = q.build()
        return conn.execute(sql, params).fetchone()[0]


def query[T: DataclassInstance](table: str, model: type[T] | None = None) -> Query[T]:
    return Query(table, model)
