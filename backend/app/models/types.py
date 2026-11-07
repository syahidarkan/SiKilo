"""Tipe kolom bersama untuk model WASKITA (portabel SQLite & PostgreSQL)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.types import TypeDecorator

# BIGINT autoincrement di Postgres; SQLite hanya meng-autoincrement INTEGER.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """
    DateTime yang selalu disimpan & dikembalikan sebagai UTC tz-aware.

    SQLite tidak menyimpan zona waktu, jadi nilai yang dibaca dari SQLite
    diberi tzinfo UTC kembali. Nilai naive saat ditulis dianggap UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
