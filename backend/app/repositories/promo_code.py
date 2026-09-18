"""Persistence layer for private one-time promotional campaigns."""

from uuid import UUID

from app.db.models import PromoCampaign, PromoRedemption
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class PromoCodeRepository:
    """Database access without owning commit/rollback boundaries."""

    @staticmethod
    def get_campaign(
        db: Session,
        *,
        campaign_id: UUID,
        for_update: bool = False,
    ) -> PromoCampaign | None:
        statement = select(PromoCampaign).where(
            PromoCampaign.id == campaign_id
        )

        if for_update:
            statement = statement.with_for_update()

        return db.scalar(statement)

    @staticmethod
    def get_campaign_by_digest(
        db: Session,
        *,
        audience: str,
        code_digest: str,
        published_only: bool = True,
        for_update: bool = False,
    ) -> PromoCampaign | None:
        statement = select(PromoCampaign).where(
            PromoCampaign.audience == audience,
            PromoCampaign.code_digest == code_digest,
        )

        if published_only:
            statement = statement.where(
                PromoCampaign.status == "published"
            )

        if for_update:
            statement = statement.with_for_update()

        return db.scalar(statement)

    @staticmethod
    def list_campaigns(
        db: Session,
        *,
        audience: str | None = None,
    ) -> list[PromoCampaign]:
        statement = select(PromoCampaign)

        if audience is not None:
            statement = statement.where(
                PromoCampaign.audience == audience
            )

        statement = statement.order_by(
            PromoCampaign.created_at.desc()
        )

        return list(db.scalars(statement).all())

    @staticmethod
    def retire_published_for_audience(
        db: Session,
        *,
        audience: str,
    ) -> list[PromoCampaign]:
        statement = (
            select(PromoCampaign)
            .where(
                PromoCampaign.audience == audience,
                PromoCampaign.status == "published",
            )
            .with_for_update()
        )

        return list(db.scalars(statement).all())

    @staticmethod
    def get_redemption(
        db: Session,
        *,
        user_id: UUID,
        audience: str,
        for_update: bool = False,
    ) -> PromoRedemption | None:
        statement = select(PromoRedemption).where(
            PromoRedemption.user_id == user_id,
            PromoRedemption.audience == audience,
        )

        if for_update:
            statement = statement.with_for_update()

        return db.scalar(statement)

    @staticmethod
    def get_redemption_by_id(
        db: Session,
        *,
        redemption_id: UUID,
        for_update: bool = False,
    ) -> PromoRedemption | None:
        statement = select(PromoRedemption).where(
            PromoRedemption.id == redemption_id
        )

        if for_update:
            statement = statement.with_for_update()

        return db.scalar(statement)

    @staticmethod
    def count_redeemed_for_campaign(
        db: Session,
        *,
        campaign_id: UUID,
    ) -> int:
        value = db.scalar(
            select(
                func.count(PromoRedemption.id)
            ).where(
                PromoRedemption.campaign_id == campaign_id,
                PromoRedemption.status == "redeemed",
            )
        )

        return int(value or 0)
