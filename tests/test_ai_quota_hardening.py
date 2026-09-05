"""SUB-3C quota stale-recovery and HTTP idempotency hardening tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.models import AIQuotaOperation, AIQuotaPeriod, ProcessingJob
from app.repositories.processing_job import ProcessingJobRepository
from app.services.ai_quota import (
    FEATURE_APPLICATION_SUPPORT,
    FEATURE_MATCH_EXPLANATION,
    AIQuotaIdempotencyConflictError,
)
from app.services.ai_quota_integration import (
    SYNC_AI_RESERVATION_STALE_SECONDS,
    build_ai_request_fingerprint,
    get_http_idempotent_job_ai_quota,
    release_stale_sync_ai_quota_reservations,
    reserve_http_idempotent_job_ai_quota,
    reserve_job_ai_quota,
    reserve_sync_ai_quota,
)

from tests.db import TestingSessionLocal


def _cleanup_user(user_id) -> None:
    db = TestingSessionLocal()

    try:
        db.query(AIQuotaOperation).filter(
            AIQuotaOperation.user_id == user_id
        ).delete(synchronize_session=False)

        db.query(AIQuotaPeriod).filter(
            AIQuotaPeriod.user_id == user_id
        ).delete(synchronize_session=False)

        db.query(ProcessingJob).filter(
            ProcessingJob.user_id == user_id
        ).delete(synchronize_session=False)

        db.commit()
    finally:
        db.close()


def test_http_idempotency_resolves_same_request_to_same_job():
    user_id = uuid4()
    db = TestingSessionLocal()

    try:
        job = ProcessingJobRepository.create(
            db=db,
            user_id=user_id,
            job_type="application_generation",
        )

        fingerprint = build_ai_request_fingerprint(
            {
                "match_id": str(uuid4()),
                "tone": "professional",
                "content_locale": "en",
            }
        )

        first = reserve_http_idempotent_job_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_APPLICATION_SUPPORT,
            job_id=job.id,
            raw_idempotency_key="request-123",
            request_fingerprint=fingerprint,
        )

        db.commit()

        found = get_http_idempotent_job_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_APPLICATION_SUPPORT,
            raw_idempotency_key="request-123",
            request_fingerprint=fingerprint,
        )

        assert found is not None
        assert found["job"].id == job.id
        assert found["operation"].id == first["operation"].id
        assert found["operation"].processing_job_id == job.id
        assert "request-123" not in found["operation"].idempotency_key
    finally:
        db.close()
        _cleanup_user(user_id)


def test_http_idempotency_same_key_different_request_conflicts():
    user_id = uuid4()
    db = TestingSessionLocal()

    try:
        job = ProcessingJobRepository.create(
            db=db,
            user_id=user_id,
            job_type="application_generation",
        )

        first_fingerprint = build_ai_request_fingerprint(
            {"match_id": "one"}
        )

        reserve_http_idempotent_job_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_APPLICATION_SUPPORT,
            job_id=job.id,
            raw_idempotency_key="same-key",
            request_fingerprint=first_fingerprint,
        )

        db.commit()

        with pytest.raises(
            AIQuotaIdempotencyConflictError
        ):
            get_http_idempotent_job_ai_quota(
                db,
                user_id=user_id,
                feature_key=FEATURE_APPLICATION_SUPPORT,
                raw_idempotency_key="same-key",
                request_fingerprint=build_ai_request_fingerprint(
                    {"match_id": "different"}
                ),
            )
    finally:
        db.close()
        _cleanup_user(user_id)


def test_stale_sync_reservation_is_released_before_new_reserve():
    user_id = uuid4()
    db = TestingSessionLocal()

    try:
        first = reserve_sync_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="stale-sync-1",
            request_fingerprint="fp-1",
        )
        db.commit()

        old_operation_id = first["operation"].id

        operation = db.get(
            AIQuotaOperation,
            old_operation_id,
        )
        operation.reserved_at = (
            datetime.now(timezone.utc)
            - timedelta(
                seconds=(
                    SYNC_AI_RESERVATION_STALE_SECONDS
                    + 60
                )
            )
        )
        db.commit()

        second = reserve_sync_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="fresh-sync-2",
            request_fingerprint="fp-2",
        )
        db.commit()

        db.expire_all()

        old_operation = db.get(
            AIQuotaOperation,
            old_operation_id,
        )
        new_operation = db.get(
            AIQuotaOperation,
            second["operation"].id,
        )
        period = (
            db.query(AIQuotaPeriod)
            .filter(
                AIQuotaPeriod.user_id == user_id,
                AIQuotaPeriod.feature_key
                == FEATURE_MATCH_EXPLANATION,
            )
            .one()
        )

        assert old_operation.status == "released"
        assert (
            old_operation.release_reason
            == "stale_sync_reservation"
        )
        assert new_operation.status == "reserved"
        assert period.used_count == 0
        assert period.reserved_count == 1
    finally:
        db.close()
        _cleanup_user(user_id)


def test_fresh_sync_reservation_is_not_released():
    user_id = uuid4()
    db = TestingSessionLocal()

    try:
        first = reserve_sync_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="fresh-1",
            request_fingerprint="fresh-fp-1",
        )
        db.commit()

        second = reserve_sync_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="fresh-2",
            request_fingerprint="fresh-fp-2",
        )
        db.commit()

        db.expire_all()

        first_operation = db.get(
            AIQuotaOperation,
            first["operation"].id,
        )
        second_operation = db.get(
            AIQuotaOperation,
            second["operation"].id,
        )
        period = db.query(AIQuotaPeriod).one()

        assert first_operation.status == "reserved"
        assert second_operation.status == "reserved"
        assert period.reserved_count == 2
        assert period.used_count == 0
    finally:
        db.close()
        _cleanup_user(user_id)


def test_stale_cleanup_never_age_releases_async_job():
    user_id = uuid4()
    db = TestingSessionLocal()

    try:
        job = ProcessingJobRepository.create(
            db=db,
            user_id=user_id,
            job_type="application_generation",
        )

        reservation = reserve_job_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_APPLICATION_SUPPORT,
            job_id=job.id,
        )
        db.commit()

        operation_id = reservation["operation"].id

        operation = db.get(
            AIQuotaOperation,
            operation_id,
        )
        operation.reserved_at = (
            datetime.now(timezone.utc)
            - timedelta(days=7)
        )
        db.commit()

        released = (
            release_stale_sync_ai_quota_reservations(
                db,
                user_id=user_id,
                feature_key=FEATURE_APPLICATION_SUPPORT,
                now=datetime.now(timezone.utc),
            )
        )
        db.commit()

        db.expire_all()

        operation = db.get(
            AIQuotaOperation,
            operation_id,
        )
        period = db.query(AIQuotaPeriod).one()

        assert released == 0
        assert operation.status == "reserved"
        assert operation.processing_job_id == job.id
        assert period.reserved_count == 1
    finally:
        db.close()
        _cleanup_user(user_id)


def test_async_http_endpoints_expose_idempotency_key():
    profile_source = Path(
        "backend/app/api/v1/endpoints/profile.py"
    ).read_text(encoding="utf-8")

    application_source = Path(
        "backend/app/api/v1/endpoints/applications.py"
    ).read_text(encoding="utf-8")

    main_source = Path(
        "backend/app/main.py"
    ).read_text(encoding="utf-8")

    assert 'alias="Idempotency-Key"' in profile_source
    assert (
        "get_http_idempotent_job_ai_quota("
        in profile_source
    )
    assert (
        "reserve_http_idempotent_job_ai_quota("
        in profile_source
    )

    assert (
        'alias="Idempotency-Key"'
        in application_source
    )
    assert (
        "get_http_idempotent_job_ai_quota("
        in application_source
    )
    assert (
        "reserve_http_idempotent_job_ai_quota("
        in application_source
    )

    assert (
        "@app.exception_handler("
        "AIQuotaIdempotencyConflictError)"
        in main_source
    )
    assert "status_code=409" in main_source
