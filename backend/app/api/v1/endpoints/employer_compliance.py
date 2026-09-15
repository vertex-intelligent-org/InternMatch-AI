"""
Employer compliance claim and evidence API.

Organization identity verification is intentionally separate from these
jurisdiction-scoped compliance claims.

Raw storage paths and private administrative notes are never returned.
"""

import re
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from app.core.rate_limit import enforce_rate_limit
from app.core.security import (
    AuthenticatedUser,
    require_admin_user,
    require_employer_user,
)
from app.db.models import (
    EmployerComplianceClaim,
    EmployerComplianceEvidence,
)
from app.db.session import get_db
from app.repositories.employer_compliance import (
    EmployerComplianceRepository,
)
from app.repositories.employer_organization import (
    EmployerOrganizationRepository,
)
from app.repositories.notification import NotificationRepository
from app.services.employer_compliance_storage import (
    MAX_COMPLIANCE_EVIDENCE_SIZE_BYTES,
    ComplianceStorageValidationError,
    delete_compliance_evidence,
    download_compliance_evidence,
    store_compliance_evidence,
)
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

employer_router = APIRouter()
admin_router = APIRouter()


ClaimType = Literal[
    "insurance_arrangement",
    "completion_certificate",
    "university_agreement",
    "legal_internship_eligibility",
]

ClaimStatus = Literal[
    "draft",
    "pending",
    "approved",
    "rejected",
    "revoked",
    "expired",
]

ReviewRejectionCode = Literal[
    "document_unreadable",
    "insufficient_evidence",
    "jurisdiction_mismatch",
    "scope_mismatch",
    "expired_evidence",
    "unsupported_claim",
    "other",
]


class ComplianceEvidenceResponse(BaseModel):
    id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class ComplianceClaimResponse(BaseModel):
    id: UUID
    organization_id: UUID
    claim_type: ClaimType
    jurisdiction_country_code: str
    scope_key: str
    scope_label: Optional[str]
    statement: Optional[str]
    status: ClaimStatus
    version: int
    submitted_at: Optional[datetime]
    reviewed_at: Optional[datetime]
    rejection_reason_code: Optional[str]
    valid_from: Optional[date]
    valid_until: Optional[date]
    created_at: datetime
    updated_at: datetime
    evidence: list[ComplianceEvidenceResponse]


class ComplianceClaimCreateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    claim_type: ClaimType
    jurisdiction_country_code: str
    scope_key: str = "organization"
    scope_label: Optional[str] = None
    statement: Optional[str] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None


class ComplianceClaimUpdateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    expected_version: int
    scope_label: Optional[str] = None
    statement: Optional[str] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None


class ComplianceMutationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    expected_version: int


class ComplianceAdminApprovalRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    expected_version: int
    internal_note: Optional[str] = None


class ComplianceAdminRejectionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    expected_version: int
    reason_code: ReviewRejectionCode
    internal_note: Optional[str] = None


class ComplianceAdminRevocationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    expected_version: int
    reason_code: str
    internal_note: Optional[str] = None






def _clean_optional(
    value: Optional[str],
    *,
    max_length: int,
) -> Optional[str]:
    if value is None:
        return None

    cleaned = value.strip()

    if not cleaned:
        return None

    if len(cleaned) > max_length:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                f"Value exceeds maximum length "
                f"of {max_length} characters."
            ),
        )

    return cleaned


def _normalize_country_code(
    value: str,
) -> str:
    cleaned = (
        value.strip().upper()
        if isinstance(value, str)
        else ""
    )

    if not re.fullmatch(
        r"[A-Z]{2}",
        cleaned,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "jurisdiction_country_code must "
                "be a two-letter country code."
            ),
        )

    return cleaned


def _normalize_scope_key(
    value: str,
) -> str:
    cleaned = (
        value.strip().lower()
        if isinstance(value, str)
        else ""
    )

    if not re.fullmatch(
        r"[a-z0-9][a-z0-9._:-]{0,99}",
        cleaned,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "scope_key must be 1-100 characters "
                "using lowercase letters, numbers, "
                "dot, underscore, colon, or hyphen."
            ),
        )

    return cleaned


def _validate_validity(
    valid_from: Optional[date],
    valid_until: Optional[date],
) -> None:
    if (
        valid_from is not None
        and valid_until is not None
        and valid_until < valid_from
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "valid_until cannot be before "
                "valid_from."
            ),
        )


def _require_organization(
    db: Session,
    current_user: AuthenticatedUser,
):
    organization = (
        EmployerOrganizationRepository
        .get_by_owner_user_id(
            db,
            current_user.user_id,
        )
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Employer organization profile "
                "not found."
            ),
        )

    return organization


def _claim_response(
    claim: EmployerComplianceClaim,
    evidence: list[
        EmployerComplianceEvidence
    ],
) -> ComplianceClaimResponse:
    return ComplianceClaimResponse(
        id=claim.id,
        organization_id=claim.organization_id,
        claim_type=claim.claim_type,
        jurisdiction_country_code=(
            claim.jurisdiction_country_code
        ),
        scope_key=claim.scope_key,
        scope_label=claim.scope_label,
        statement=claim.statement,
        status=claim.status,
        version=claim.version,
        submitted_at=claim.submitted_at,
        reviewed_at=claim.reviewed_at,
        rejection_reason_code=(
            claim.rejection_reason_code
        ),
        valid_from=claim.valid_from,
        valid_until=claim.valid_until,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
        evidence=[
            ComplianceEvidenceResponse(
                id=item.id,
                original_filename=(
                    item.original_filename
                ),
                content_type=item.content_type,
                size_bytes=item.size_bytes,
                created_at=item.created_at,
            )
            for item in evidence
        ],
    )


def _claims_response(
    db: Session,
    claims: list[
        EmployerComplianceClaim
    ],
) -> list[ComplianceClaimResponse]:
    claim_ids = [
        claim.id
        for claim in claims
    ]

    evidence_rows = (
        EmployerComplianceRepository
        .list_evidence_for_claim_ids(
            db,
            claim_ids,
        )
    )

    by_claim = defaultdict(list)

    for item in evidence_rows:
        by_claim[item.claim_id].append(
            item
        )

    return [
        _claim_response(
            claim,
            by_claim.get(claim.id, []),
        )
        for claim in claims
    ]


def _assert_version(
    claim: EmployerComplianceClaim,
    expected_version: int,
) -> None:
    if (
        not isinstance(expected_version, int)
        or expected_version < 1
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail="expected_version must be positive.",
        )

    if claim.version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Compliance claim changed while this "
                "request was being processed. Refresh "
                "and try again."
            ),
        )


def _owned_claim(
    db: Session,
    *,
    organization_id: UUID,
    claim_id: UUID,
):
    claim = (
        EmployerComplianceRepository.get_claim(
            db,
            claim_id,
        )
    )

    if (
        claim is None
        or claim.organization_id
        != organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compliance claim not found.",
        )

    return claim


def _owned_claim_for_update(
    db: Session,
    *,
    organization_id: UUID,
    claim_id: UUID,
):
    claim = (
        EmployerComplianceRepository
        .get_claim_for_update(
            db,
            claim_id,
        )
    )

    if (
        claim is None
        or claim.organization_id
        != organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compliance claim not found.",
        )

    return claim


def _evidence_for_claim(
    db: Session,
    *,
    claim_id: UUID,
    evidence_id: UUID,
):
    evidence = (
        EmployerComplianceRepository
        .get_evidence(
            db,
            evidence_id,
        )
    )

    if (
        evidence is None
        or evidence.claim_id != claim_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compliance evidence not found.",
        )

    return evidence


@employer_router.get(
    "/claims",
    response_model=list[
        ComplianceClaimResponse
    ],
)
def list_my_compliance_claims(
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    organization = _require_organization(
        db,
        current_user,
    )

    claims = (
        EmployerComplianceRepository
        .list_claims_for_organization(
            db,
            organization.id,
        )
    )

    return _claims_response(
        db,
        claims,
    )


@employer_router.post(
    "/claims",
    response_model=ComplianceClaimResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_compliance_claim(
    payload: ComplianceClaimCreateRequest,
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    organization = _require_organization(
        db,
        current_user,
    )

    country_code = _normalize_country_code(
        payload.jurisdiction_country_code
    )

    scope_key = _normalize_scope_key(
        payload.scope_key
    )

    scope_label = _clean_optional(
        payload.scope_label,
        max_length=200,
    )

    statement = _clean_optional(
        payload.statement,
        max_length=2000,
    )

    _validate_validity(
        payload.valid_from,
        payload.valid_until,
    )

    try:
        claim = (
            EmployerComplianceRepository
            .create_claim(
                db,
                organization_id=organization.id,
                claim_type=payload.claim_type,
                jurisdiction_country_code=(
                    country_code
                ),
                scope_key=scope_key,
                scope_label=scope_label,
                statement=statement,
                valid_from=payload.valid_from,
                valid_until=payload.valid_until,
            )
        )

        EmployerComplianceRepository.record_event(
            db,
            claim_id=claim.id,
            actor_user_id=current_user.user_id,
            actor_role="employer",
            action="created",
            previous_status=None,
            new_status="draft",
        )

        db.commit()
        db.refresh(claim)
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A compliance claim already exists "
                "for this organization, type, "
                "jurisdiction, and scope."
            ),
        )
    except Exception:
        db.rollback()
        raise

    return _claim_response(
        claim,
        [],
    )


@employer_router.put(
    "/claims/{claim_id}",
    response_model=ComplianceClaimResponse,
)
def update_compliance_claim(
    claim_id: UUID,
    payload: ComplianceClaimUpdateRequest,
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    organization = _require_organization(
        db,
        current_user,
    )

    scope_label = _clean_optional(
        payload.scope_label,
        max_length=200,
    )

    statement = _clean_optional(
        payload.statement,
        max_length=2000,
    )

    _validate_validity(
        payload.valid_from,
        payload.valid_until,
    )

    try:
        claim = _owned_claim_for_update(
            db,
            organization_id=organization.id,
            claim_id=claim_id,
        )

        _assert_version(
            claim,
            payload.expected_version,
        )

        if claim.status not in {
            "draft",
            "rejected",
        }:
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                ),
                detail=(
                    "Only draft or rejected compliance "
                    "claims may be edited."
                ),
            )

        previous_status = claim.status

        EmployerComplianceRepository.update_claim_details(
            db,
            claim,
            scope_label=scope_label,
            statement=statement,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
        )

        EmployerComplianceRepository.record_event(
            db,
            claim_id=claim.id,
            actor_user_id=current_user.user_id,
            actor_role="employer",
            action="updated",
            previous_status=previous_status,
            new_status=claim.status,
        )

        db.commit()
        db.refresh(claim)
    except Exception:
        db.rollback()
        raise

    evidence = (
        EmployerComplianceRepository
        .list_evidence_for_claim(
            db,
            claim.id,
        )
    )

    return _claim_response(
        claim,
        evidence,
    )


@employer_router.post(
    "/claims/{claim_id}/evidence",
    response_model=ComplianceClaimResponse,
)
async def upload_compliance_evidence(
    claim_id: UUID,
    expected_version: int = Query(..., ge=1),
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    organization = _require_organization(
        db,
        current_user,
    )

    claim = _owned_claim(
        db,
        organization_id=organization.id,
        claim_id=claim_id,
    )

    _assert_version(
        claim,
        expected_version,
    )

    if claim.status not in {
        "draft",
        "rejected",
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Evidence may only be attached to "
                "draft or rejected claims."
            ),
        )

    enforce_rate_limit(
        user_id=current_user.user_id,
        scope="compliance_evidence_upload",
    )

    content = await file.read(
        MAX_COMPLIANCE_EVIDENCE_SIZE_BYTES
        + 1
    )

    if (
        len(content)
        > MAX_COMPLIANCE_EVIDENCE_SIZE_BYTES
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_413_CONTENT_TOO_LARGE
            ),
            detail=(
                "Compliance evidence exceeds "
                "maximum limit of 10 MB."
            ),
        )

    try:
        stored = store_compliance_evidence(
            organization_id=organization.id,
            claim_id=claim.id,
            filename=file.filename or "",
            content_type=file.content_type or "",
            content=content,
        )
    except ComplianceStorageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Compliance evidence storage is "
                "temporarily unavailable."
            ),
        )

    try:
        locked = _owned_claim_for_update(
            db,
            organization_id=organization.id,
            claim_id=claim.id,
        )

        _assert_version(
            locked,
            expected_version,
        )

        if locked.status not in {
            "draft",
            "rejected",
        }:
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                ),
                detail=(
                    "Claim status changed while "
                    "evidence was uploading."
                ),
            )

        EmployerComplianceRepository.add_evidence(
            db,
            claim_id=locked.id,
            storage_path=stored.storage_path,
            original_filename=(
                file.filename or "evidence.pdf"
            ),
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            sha256_hex=stored.sha256_hex,
            uploaded_by_user_id=(
                current_user.user_id
            ),
        )

        EmployerComplianceRepository.bump_claim_version(
            db,
            locked,
        )

        EmployerComplianceRepository.record_event(
            db,
            claim_id=locked.id,
            actor_user_id=current_user.user_id,
            actor_role="employer",
            action="evidence_attached",
            previous_status=locked.status,
            new_status=locked.status,
        )

        db.commit()
        db.refresh(locked)
    except Exception:
        db.rollback()

        try:
            delete_compliance_evidence(
                organization_id=organization.id,
                claim_id=claim.id,
                storage_path=stored.storage_path,
            )
        except Exception:
            pass

        raise

    evidence = (
        EmployerComplianceRepository
        .list_evidence_for_claim(
            db,
            locked.id,
        )
    )

    return _claim_response(
        locked,
        evidence,
    )


@employer_router.get(
    "/claims/{claim_id}/evidence/{evidence_id}/content"
)
def download_my_compliance_evidence_content(
    claim_id: UUID,
    evidence_id: UUID,
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    organization = _require_organization(
        db,
        current_user,
    )
    claim = _owned_claim(
        db,
        organization_id=organization.id,
        claim_id=claim_id,
    )
    evidence = _evidence_for_claim(
        db,
        claim_id=claim.id,
        evidence_id=evidence_id,
    )
    try:
        document_bytes = download_compliance_evidence(
            organization_id=organization.id,
            claim_id=claim.id,
            storage_path=evidence.storage_path,
        )
    except ComplianceStorageValidationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Compliance evidence is temporarily unavailable."
            ),
        )

    return Response(
        content=document_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                'inline; filename="compliance-evidence.pdf"'
            ),
            "Cache-Control": (
                "private, no-store, max-age=0"
            ),
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )



@employer_router.post(
    "/claims/{claim_id}/submit",
    response_model=ComplianceClaimResponse,
)
def submit_compliance_claim(
    claim_id: UUID,
    payload: ComplianceMutationRequest,
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    organization = _require_organization(
        db,
        current_user,
    )

    try:
        claim = _owned_claim_for_update(
            db,
            organization_id=organization.id,
            claim_id=claim_id,
        )

        _assert_version(
            claim,
            payload.expected_version,
        )

        if claim.status not in {
            "draft",
            "rejected",
        }:
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                ),
                detail=(
                    "Only draft or rejected claims "
                    "may be submitted."
                ),
            )

        evidence = (
            EmployerComplianceRepository
            .list_evidence_for_claim(
                db,
                claim.id,
            )
        )

        if not evidence:
            raise HTTPException(
                status_code=(
                    status.HTTP_422_UNPROCESSABLE_ENTITY
                ),
                detail=(
                    "At least one supporting evidence "
                    "document is required."
                ),
            )

        if (
            claim.valid_until is not None
            and claim.valid_until
            < datetime.now(
                timezone.utc
            ).date()
        ):
            raise HTTPException(
                status_code=(
                    status.HTTP_422_UNPROCESSABLE_ENTITY
                ),
                detail=(
                    "Expired compliance evidence "
                    "cannot be submitted."
                ),
            )

        previous_status = claim.status
        now = datetime.now(timezone.utc)

        EmployerComplianceRepository.transition_status(
            db,
            claim,
            new_status="pending",
            submitted_at=now,
            reviewed_at=None,
            reviewed_by=None,
            rejection_reason_code=None,
        )

        EmployerComplianceRepository.record_event(
            db,
            claim_id=claim.id,
            actor_user_id=current_user.user_id,
            actor_role="employer",
            action="submitted",
            previous_status=previous_status,
            new_status="pending",
        )

        db.commit()
        db.refresh(claim)
    except Exception:
        db.rollback()
        raise

    evidence = (
        EmployerComplianceRepository
        .list_evidence_for_claim(
            db,
            claim.id,
        )
    )

    return _claim_response(
        claim,
        evidence,
    )


@admin_router.get(
    "/claims",
    response_model=list[
        ComplianceClaimResponse
    ],
)
def list_compliance_claims_for_review(
    claim_status: ClaimStatus = Query(
        "pending",
        alias="status",
    ),
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    claims = (
        EmployerComplianceRepository
        .list_claims_by_status(
            db,
            claim_status,
        )
    )

    return _claims_response(
        db,
        claims,
    )


@admin_router.get(
    "/claims/{claim_id}",
    response_model=ComplianceClaimResponse,
)
def get_compliance_claim_for_review(
    claim_id: UUID,
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    claim = (
        EmployerComplianceRepository
        .get_claim(
            db,
            claim_id,
        )
    )

    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compliance claim not found.",
        )

    evidence = (
        EmployerComplianceRepository
        .list_evidence_for_claim(
            db,
            claim.id,
        )
    )

    return _claim_response(
        claim,
        evidence,
    )


@admin_router.get(
    "/claims/{claim_id}/evidence/{evidence_id}/content"
)
def download_admin_compliance_evidence_content(
    claim_id: UUID,
    evidence_id: UUID,
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    claim = EmployerComplianceRepository.get_claim(
        db,
        claim_id,
    )
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compliance claim not found.",
        )

    evidence = _evidence_for_claim(
        db,
        claim_id=claim.id,
        evidence_id=evidence_id,
    )
    try:
        document_bytes = download_compliance_evidence(
            organization_id=claim.organization_id,
            claim_id=claim.id,
            storage_path=evidence.storage_path,
        )
    except ComplianceStorageValidationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Compliance evidence is temporarily unavailable."
            ),
        )

    return Response(
        content=document_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                'inline; filename="compliance-evidence.pdf"'
            ),
            "Cache-Control": (
                "private, no-store, max-age=0"
            ),
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )



@admin_router.post(
    "/claims/{claim_id}/approve",
    response_model=ComplianceClaimResponse,
)
def approve_compliance_claim(
    claim_id: UUID,
    payload: ComplianceAdminApprovalRequest,
    admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    internal_note = _clean_optional(
        payload.internal_note,
        max_length=2000,
    )

    try:
        claim = (
            EmployerComplianceRepository
            .get_claim_for_update(
                db,
                claim_id,
            )
        )

        if claim is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Compliance claim not found.",
            )

        _assert_version(
            claim,
            payload.expected_version,
        )

        if claim.status != "pending":
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                ),
                detail=(
                    "Only pending compliance claims "
                    "may be approved."
                ),
            )

        evidence = (
            EmployerComplianceRepository
            .list_evidence_for_claim(
                db,
                claim.id,
            )
        )

        if not evidence:
            raise HTTPException(
                status_code=(
                    status.HTTP_422_UNPROCESSABLE_ENTITY
                ),
                detail=(
                    "Supporting evidence is required "
                    "before approval."
                ),
            )

        now = datetime.now(timezone.utc)

        EmployerComplianceRepository.transition_status(
            db,
            claim,
            new_status="approved",
            reviewed_at=now,
            reviewed_by=admin_user.user_id,
            rejection_reason_code=None,
        )

        EmployerComplianceRepository.record_event(
            db,
            claim_id=claim.id,
            actor_user_id=admin_user.user_id,
            actor_role="admin",
            action="approved",
            previous_status="pending",
            new_status="approved",
            internal_note=internal_note,
        )

        NotificationRepository.create_for_organization_owner(
            db,
            organization_id=claim.organization_id,
            event_type="compliance_approved",
            entity_type="employer_compliance_claim",
            entity_id=claim.id,
            data={
                "claim_id": str(
                    claim.id
                ),
                "organization_id": str(
                    claim.organization_id
                ),
                "status": "approved",
            },
            dedupe_key=(
                f"compliance:{claim.id}:"
                f"approved:v{claim.version}"
            ),
        )

        db.commit()
        db.refresh(claim)
    except Exception:
        db.rollback()
        raise

    evidence = (
        EmployerComplianceRepository
        .list_evidence_for_claim(
            db,
            claim.id,
        )
    )

    return _claim_response(
        claim,
        evidence,
    )


@admin_router.post(
    "/claims/{claim_id}/reject",
    response_model=ComplianceClaimResponse,
)
def reject_compliance_claim(
    claim_id: UUID,
    payload: ComplianceAdminRejectionRequest,
    admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    internal_note = _clean_optional(
        payload.internal_note,
        max_length=2000,
    )

    try:
        claim = (
            EmployerComplianceRepository
            .get_claim_for_update(
                db,
                claim_id,
            )
        )

        if claim is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Compliance claim not found.",
            )

        _assert_version(
            claim,
            payload.expected_version,
        )

        if claim.status != "pending":
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                ),
                detail=(
                    "Only pending compliance claims "
                    "may be rejected."
                ),
            )

        now = datetime.now(timezone.utc)

        EmployerComplianceRepository.transition_status(
            db,
            claim,
            new_status="rejected",
            reviewed_at=now,
            reviewed_by=admin_user.user_id,
            rejection_reason_code=(
                payload.reason_code
            ),
        )

        EmployerComplianceRepository.record_event(
            db,
            claim_id=claim.id,
            actor_user_id=admin_user.user_id,
            actor_role="admin",
            action="rejected",
            previous_status="pending",
            new_status="rejected",
            reason_code=payload.reason_code,
            internal_note=internal_note,
        )

        NotificationRepository.create_for_organization_owner(
            db,
            organization_id=claim.organization_id,
            event_type="compliance_rejected",
            entity_type="employer_compliance_claim",
            entity_id=claim.id,
            data={
                "claim_id": str(
                    claim.id
                ),
                "organization_id": str(
                    claim.organization_id
                ),
                "status": "rejected",
            },
            dedupe_key=(
                f"compliance:{claim.id}:"
                f"rejected:v{claim.version}"
            ),
        )

        db.commit()
        db.refresh(claim)
    except Exception:
        db.rollback()
        raise

    evidence = (
        EmployerComplianceRepository
        .list_evidence_for_claim(
            db,
            claim.id,
        )
    )

    return _claim_response(
        claim,
        evidence,
    )


@admin_router.post(
    "/claims/{claim_id}/revoke",
    response_model=ComplianceClaimResponse,
)
def revoke_compliance_claim(
    claim_id: UUID,
    payload: ComplianceAdminRevocationRequest,
    admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    reason_code = (
        payload.reason_code.strip()
        if isinstance(
            payload.reason_code,
            str,
        )
        else ""
    )

    if (
        not reason_code
        or len(reason_code) > 100
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "reason_code is required and must "
                "not exceed 100 characters."
            ),
        )

    internal_note = _clean_optional(
        payload.internal_note,
        max_length=2000,
    )

    try:
        claim = (
            EmployerComplianceRepository
            .get_claim_for_update(
                db,
                claim_id,
            )
        )

        if claim is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Compliance claim not found.",
            )

        _assert_version(
            claim,
            payload.expected_version,
        )

        if claim.status != "approved":
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                ),
                detail=(
                    "Only approved compliance claims "
                    "may be revoked."
                ),
            )

        now = datetime.now(timezone.utc)

        EmployerComplianceRepository.transition_status(
            db,
            claim,
            new_status="revoked",
            reviewed_at=now,
            reviewed_by=admin_user.user_id,
            rejection_reason_code=None,
        )

        EmployerComplianceRepository.record_event(
            db,
            claim_id=claim.id,
            actor_user_id=admin_user.user_id,
            actor_role="admin",
            action="revoked",
            previous_status="approved",
            new_status="revoked",
            reason_code=reason_code,
            internal_note=internal_note,
        )

        db.commit()
        db.refresh(claim)
    except Exception:
        db.rollback()
        raise

    evidence = (
        EmployerComplianceRepository
        .list_evidence_for_claim(
            db,
            claim.id,
        )
    )

    return _claim_response(
        claim,
        evidence,
    )
