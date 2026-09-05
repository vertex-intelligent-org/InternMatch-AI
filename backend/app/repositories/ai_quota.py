"""Persistence boundary for backend-owned AI quota state."""

import hashlib
from datetime import datetime
from uuid import UUID

from app.db.models import AIQuotaOperation, AIQuotaPeriod
from sqlalchemy import select, text
from sqlalchemy.orm import Session


class AIQuotaRepository:
    """Read/write boundary for quota periods and operation lifecycle."""

    @staticmethod
    def acquire_feature_lock(
        db: Session,
        *,
        user_id: UUID,
        feature_key: str,
    ) -> None:
        """Serialize one user's feature quota mutations in PostgreSQL.

        PostgreSQL advisory transaction locks also protect the first-use case
        where no AIQuotaPeriod row exists yet. SQLite tests execute
        single-process and therefore do not require this provider lock.
        """

        bind = db.get_bind()

        if bind.dialect.name != "postgresql":
            return

        lock_material = (
            f"internmatch:ai-quota:{user_id}:{feature_key}"
        ).encode("utf-8")

        digest = hashlib.blake2b(
            lock_material,
            digest_size=8,
        ).digest()

        lock_key = int.from_bytes(
            digest,
            byteorder="big",
            signed=True,
        )

        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    @staticmethod
    def list_active_periods(
        db: Session,
        *,
        user_id: UUID,
        plan_key: str,
        now: datetime,
    ) -> list[AIQuotaPeriod]:
        stmt = (
            select(AIQuotaPeriod)
            .where(
                AIQuotaPeriod.user_id == user_id,
                AIQuotaPeriod.plan_key == plan_key,
                AIQuotaPeriod.period_start <= now,
                AIQuotaPeriod.period_end > now,
            )
            .order_by(
                AIQuotaPeriod.feature_key.asc(),
                AIQuotaPeriod.period_start.desc(),
            )
        )

        return list(db.scalars(stmt).all())

    @staticmethod
    def get_feature_period(
        db: Session,
        *,
        user_id: UUID,
        feature_key: str,
        for_update: bool = False,
    ) -> AIQuotaPeriod | None:
        stmt = select(AIQuotaPeriod).where(
            AIQuotaPeriod.user_id == user_id,
            AIQuotaPeriod.feature_key == feature_key,
        )

        if for_update:
            stmt = stmt.with_for_update()

        return db.scalar(stmt)

    @staticmethod
    def get_exact_period(
        db: Session,
        *,
        user_id: UUID,
        feature_key: str,
        plan_key: str,
        period_start: datetime,
        period_end: datetime,
    ) -> AIQuotaPeriod | None:
        stmt = select(AIQuotaPeriod).where(
            AIQuotaPeriod.user_id == user_id,
            AIQuotaPeriod.feature_key == feature_key,
            AIQuotaPeriod.plan_key == plan_key,
            AIQuotaPeriod.period_start == period_start,
            AIQuotaPeriod.period_end == period_end,
        )

        return db.scalar(stmt)

    @staticmethod
    def get_operation_by_key(
        db: Session,
        *,
        user_id: UUID,
        feature_key: str,
        period_start: datetime,
        idempotency_key: str,
        for_update: bool = False,
    ) -> AIQuotaOperation | None:
        stmt = select(AIQuotaOperation).where(
            AIQuotaOperation.user_id == user_id,
            AIQuotaOperation.feature_key == feature_key,
            AIQuotaOperation.period_start == period_start,
            AIQuotaOperation.idempotency_key == idempotency_key,
        )

        if for_update:
            stmt = stmt.with_for_update()

        return db.scalar(stmt)

    @staticmethod
    def get_operation_by_id(
        db: Session,
        *,
        operation_id: UUID,
        for_update: bool = False,
    ) -> AIQuotaOperation | None:
        stmt = select(AIQuotaOperation).where(
            AIQuotaOperation.id == operation_id,
        )

        if for_update:
            stmt = stmt.with_for_update()

        return db.scalar(stmt)
