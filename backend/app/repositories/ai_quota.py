"""Persistence boundary for backend-owned AI quota periods."""

from datetime import datetime
from uuid import UUID

from app.db.models import AIQuotaPeriod
from sqlalchemy import select
from sqlalchemy.orm import Session


class AIQuotaRepository:
    """Read/write boundary for aggregate feature quota periods."""

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
