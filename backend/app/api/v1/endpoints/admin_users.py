"""
Administrative user directory and audit timeline.

This surface is deliberately derived from InternMatch-owned application
records. It never reads, returns, or serializes authentication credentials,
provider tokens, private document paths, or raw CV data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from app.core.security import AuthenticatedUser, require_admin_user
from app.db.models import (
    EmployerComplianceClaim,
    EmployerComplianceEvent,
    EmployerOrganization,
    EmployerVerificationEvent,
    StudentProfile,
)
from app.db.session import get_db
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()

AdminUserRole = Literal["student", "employer"]
AdminAuditSource = Literal[
    "employer_verification",
    "employer_compliance",
]


class AdminUserSummary(BaseModel):
    user_id: UUID
    roles: list[AdminUserRole]
    display_name: str
    headline: str | None = None
    business_email: str | None = None
    organization_id: UUID | None = None
    verification_status: str | None = None
    organization_type: str | None = None
    country_code: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserSummary]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class AdminUserAuditEvent(BaseModel):
    source: AdminAuditSource
    related_id: UUID
    actor_user_id: UUID | None = None
    action: str
    previous_status: str | None = None
    new_status: str | None = None
    reason_code: str | None = None
    internal_note: str | None = None
    created_at: datetime


class AdminUserDetail(AdminUserSummary):
    audit_events: list[AdminUserAuditEvent]


def _clean_optional_text(
    value: object,
) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    return cleaned or None


def _merge_timestamp_min(
    left: datetime | None,
    right: datetime | None,
) -> datetime | None:
    values = [
        value
        for value in (left, right)
        if value is not None
    ]
    return min(values) if values else None


def _merge_timestamp_max(
    left: datetime | None,
    right: datetime | None,
) -> datetime | None:
    values = [
        value
        for value in (left, right)
        if value is not None
    ]
    return max(values) if values else None


def _summary_from_student(
    profile: StudentProfile,
) -> AdminUserSummary:
    display_name = (
        _clean_optional_text(profile.full_name)
        or str(profile.user_id)
    )

    return AdminUserSummary(
        user_id=profile.user_id,
        roles=["student"],
        display_name=display_name,
        headline=_clean_optional_text(
            profile.headline
        ),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _summary_from_organization(
    organization: EmployerOrganization,
) -> AdminUserSummary:
    display_name = (
        _clean_optional_text(
            organization.display_name
        )
        or _clean_optional_text(
            organization.legal_name
        )
        or str(organization.owner_user_id)
    )

    return AdminUserSummary(
        user_id=organization.owner_user_id,
        roles=["employer"],
        display_name=display_name,
        business_email=_clean_optional_text(
            organization.business_email
        ),
        organization_id=organization.id,
        verification_status=(
            organization.verification_status
        ),
        organization_type=(
            organization.organization_type
        ),
        country_code=organization.country_code,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


def _merge_summaries(
    left: AdminUserSummary,
    right: AdminUserSummary,
) -> AdminUserSummary:
    roles: list[AdminUserRole] = []

    for role in (
        *left.roles,
        *right.roles,
    ):
        if role not in roles:
            roles.append(role)

    employer = (
        right
        if "employer" in right.roles
        else left
    )

    student = (
        right
        if "student" in right.roles
        else left
    )

    return AdminUserSummary(
        user_id=left.user_id,
        roles=roles,
        display_name=(
            employer.display_name
            if "employer" in roles
            else student.display_name
        ),
        headline=student.headline,
        business_email=employer.business_email,
        organization_id=employer.organization_id,
        verification_status=(
            employer.verification_status
        ),
        organization_type=(
            employer.organization_type
        ),
        country_code=employer.country_code,
        created_at=_merge_timestamp_min(
            left.created_at,
            right.created_at,
        ),
        updated_at=_merge_timestamp_max(
            left.updated_at,
            right.updated_at,
        ),
    )


def _matches_query(
    item: AdminUserSummary,
    query: str,
) -> bool:
    normalized = query.casefold()

    values = (
        str(item.user_id),
        item.display_name,
        item.headline,
        item.business_email,
        str(item.organization_id)
        if item.organization_id
        else None,
        item.verification_status,
        item.organization_type,
        item.country_code,
    )

    return any(
        normalized in value.casefold()
        for value in values
        if isinstance(value, str)
        and value
    )


def _build_directory(
    *,
    students: list[StudentProfile],
    organizations: list[EmployerOrganization],
    query: str | None,
    role: AdminUserRole | None,
) -> list[AdminUserSummary]:
    by_user: dict[UUID, AdminUserSummary] = {}

    if role != "employer":
        for profile in students:
            item = _summary_from_student(
                profile
            )
            by_user[item.user_id] = item

    if role != "student":
        for organization in organizations:
            item = _summary_from_organization(
                organization
            )

            existing = by_user.get(
                item.user_id
            )

            by_user[item.user_id] = (
                _merge_summaries(
                    existing,
                    item,
                )
                if existing
                else item
            )

    items = list(by_user.values())

    if query:
        cleaned_query = query.strip()
        if cleaned_query:
            items = [
                item
                for item in items
                if _matches_query(
                    item,
                    cleaned_query,
                )
            ]

    items.sort(
        key=lambda item: (
            item.updated_at
            or item.created_at
            or datetime.min
        ),
        reverse=True,
    )

    return items


def _load_user_summary(
    db: Session,
    user_id: UUID,
) -> tuple[
    AdminUserSummary | None,
    EmployerOrganization | None,
]:
    student = db.scalar(
        select(StudentProfile).where(
            StudentProfile.user_id
            == user_id
        )
    )

    organization = db.scalar(
        select(EmployerOrganization).where(
            EmployerOrganization.owner_user_id
            == user_id
        )
    )

    summary: AdminUserSummary | None = None

    if student is not None:
        summary = _summary_from_student(
            student
        )

    if organization is not None:
        employer_summary = (
            _summary_from_organization(
                organization
            )
        )

        summary = (
            _merge_summaries(
                summary,
                employer_summary,
            )
            if summary is not None
            else employer_summary
        )

    return summary, organization


def _load_audit_events(
    db: Session,
    organization: EmployerOrganization | None,
) -> list[AdminUserAuditEvent]:
    if organization is None:
        return []

    events: list[AdminUserAuditEvent] = []

    verification_events = list(
        db.scalars(
            select(
                EmployerVerificationEvent
            )
            .where(
                EmployerVerificationEvent.organization_id
                == organization.id
            )
            .order_by(
                EmployerVerificationEvent.created_at.desc()
            )
        ).all()
    )

    for event in verification_events:
        events.append(
            AdminUserAuditEvent(
                source="employer_verification",
                related_id=organization.id,
                actor_user_id=(
                    event.reviewer_user_id
                ),
                action=event.action,
                previous_status=(
                    event.previous_status
                ),
                new_status=event.new_status,
                reason_code=event.reason_code,
                internal_note=event.internal_note,
                created_at=event.created_at,
            )
        )

    claim_ids = list(
        db.scalars(
            select(
                EmployerComplianceClaim.id
            ).where(
                EmployerComplianceClaim.organization_id
                == organization.id
            )
        ).all()
    )

    if claim_ids:
        compliance_events = list(
            db.scalars(
                select(
                    EmployerComplianceEvent
                )
                .where(
                    EmployerComplianceEvent.claim_id.in_(
                        claim_ids
                    )
                )
                .order_by(
                    EmployerComplianceEvent.created_at.desc()
                )
            ).all()
        )

        for event in compliance_events:
            events.append(
                AdminUserAuditEvent(
                    source="employer_compliance",
                    related_id=event.claim_id,
                    actor_user_id=(
                        event.actor_user_id
                    ),
                    action=event.action,
                    previous_status=(
                        event.previous_status
                    ),
                    new_status=event.new_status,
                    reason_code=event.reason_code,
                    internal_note=event.internal_note,
                    created_at=event.created_at,
                )
            )

    events.sort(
        key=lambda event: event.created_at,
        reverse=True,
    )

    return events


@router.get(
    "",
    response_model=AdminUserListResponse,
)
def list_admin_users(
    query: str | None = Query(
        default=None,
        max_length=200,
    ),
    role: AdminUserRole | None = Query(
        default=None,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    students = (
        list(
            db.scalars(
                select(StudentProfile)
            ).all()
        )
        if role != "employer"
        else []
    )

    organizations = (
        list(
            db.scalars(
                select(EmployerOrganization)
            ).all()
        )
        if role != "student"
        else []
    )

    items = _build_directory(
        students=students,
        organizations=organizations,
        query=query,
        role=role,
    )

    total = len(items)

    return AdminUserListResponse(
        items=items[
            offset:offset + limit
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{user_id}",
    response_model=AdminUserDetail,
)
def get_admin_user(
    user_id: UUID,
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    summary, organization = (
        _load_user_summary(
            db,
            user_id,
        )
    )

    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return AdminUserDetail(
        **summary.model_dump(),
        audit_events=_load_audit_events(
            db,
            organization,
        ),
    )
