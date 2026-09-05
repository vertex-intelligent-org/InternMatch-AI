"""SUB-3B1 asynchronous AI quota/job lifecycle integration tests."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.models import AIQuotaOperation, AIQuotaPeriod
from app.repositories.processing_job import ProcessingJobRepository
from app.services.ai_quota import (
    FEATURE_APPLICATION_SUPPORT,
    FEATURE_CV_ANALYSIS,
    AIQuotaExceededError,
)
from app.services.ai_quota_integration import (
    ensure_job_ai_quota_reserved_if_present,
    format_ai_quota_exceeded_payload,
    release_job_ai_quota_if_present,
    reserve_job_ai_quota,
    settle_job_ai_quota_if_present,
)

from tests.db import TestingSessionLocal


def _create_job(
    *,
    user_id,
    job_type: str,
):
    db = TestingSessionLocal()

    try:
        job = ProcessingJobRepository.create(
            db=db,
            user_id=user_id,
            job_type=job_type,
        )
        db.commit()
        db.refresh(job)
        return job.id
    finally:
        db.close()


def _cleanup_user(user_id) -> None:
    db = TestingSessionLocal()

    try:
        db.query(AIQuotaOperation).filter(
            AIQuotaOperation.user_id == user_id
        ).delete(synchronize_session=False)

        db.query(AIQuotaPeriod).filter(
            AIQuotaPeriod.user_id == user_id
        ).delete(synchronize_session=False)

        from app.db.models import ProcessingJob

        db.query(ProcessingJob).filter(
            ProcessingJob.user_id == user_id
        ).delete(synchronize_session=False)

        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize(
    ("feature_key", "job_type"),
    [
        (
            FEATURE_CV_ANALYSIS,
            "cv_extraction",
        ),
        (
            FEATURE_APPLICATION_SUPPORT,
            "application_generation",
        ),
    ],
)
def test_job_quota_reservation_is_linked_and_idempotent(
    feature_key,
    job_type,
):
    user_id = uuid4()
    job_id = _create_job(
        user_id=user_id,
        job_type=job_type,
    )

    db = TestingSessionLocal()

    try:
        first = reserve_job_ai_quota(
            db,
            user_id=user_id,
            feature_key=feature_key,
            job_id=job_id,
        )
        db.commit()

        second = reserve_job_ai_quota(
            db,
            user_id=user_id,
            feature_key=feature_key,
            job_id=job_id,
        )
        db.commit()

        assert first["outcome"] == "reserved"
        assert second["outcome"] == "duplicate_reserved"
        assert (
            first["operation"].id
            == second["operation"].id
        )

        operation = (
            db.query(AIQuotaOperation)
            .filter(
                AIQuotaOperation.user_id == user_id,
                AIQuotaOperation.feature_key == feature_key,
            )
            .one()
        )

        period = (
            db.query(AIQuotaPeriod)
            .filter(
                AIQuotaPeriod.user_id == user_id,
                AIQuotaPeriod.feature_key == feature_key,
            )
            .one()
        )

        assert operation.processing_job_id == job_id
        assert operation.status == "reserved"
        assert period.used_count == 0
        assert period.reserved_count == 1
    finally:
        db.close()
        _cleanup_user(user_id)


def test_failed_job_can_release_retry_and_settle_once():
    user_id = uuid4()
    job_id = _create_job(
        user_id=user_id,
        job_type="application_generation",
    )

    db = TestingSessionLocal()

    try:
        first = reserve_job_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_APPLICATION_SUPPORT,
            job_id=job_id,
        )
        operation_id = first["operation"].id
        db.commit()

        released = release_job_ai_quota_if_present(
            db,
            feature_key=FEATURE_APPLICATION_SUPPORT,
            job_id=job_id,
            reason="worker_failure",
        )
        db.commit()

        assert released is not None
        assert released["outcome"] == "released"

        period = db.query(AIQuotaPeriod).one()

        assert period.used_count == 0
        assert period.reserved_count == 0

        retry = ensure_job_ai_quota_reserved_if_present(
            db,
            user_id=user_id,
            feature_key=FEATURE_APPLICATION_SUPPORT,
            job_id=job_id,
        )
        db.commit()

        assert retry is not None
        assert retry["outcome"] == "re_reserved"
        assert retry["operation"].id == operation_id

        settled = settle_job_ai_quota_if_present(
            db,
            feature_key=FEATURE_APPLICATION_SUPPORT,
            job_id=job_id,
        )
        db.commit()

        duplicate_settle = settle_job_ai_quota_if_present(
            db,
            feature_key=FEATURE_APPLICATION_SUPPORT,
            job_id=job_id,
        )
        db.commit()

        assert settled is not None
        assert settled["outcome"] == "settled"

        assert duplicate_settle is not None
        assert (
            duplicate_settle["outcome"]
            == "already_settled"
        )

        db.refresh(period)

        assert period.used_count == 1
        assert period.reserved_count == 0
    finally:
        db.close()
        _cleanup_user(user_id)


def test_legacy_async_job_without_quota_operation_is_safe_noop():
    user_id = uuid4()
    job_id = _create_job(
        user_id=user_id,
        job_type="cv_extraction",
    )

    db = TestingSessionLocal()

    try:
        assert (
            settle_job_ai_quota_if_present(
                db,
                feature_key=FEATURE_CV_ANALYSIS,
                job_id=job_id,
            )
            is None
        )

        assert (
            release_job_ai_quota_if_present(
                db,
                feature_key=FEATURE_CV_ANALYSIS,
                job_id=job_id,
                reason="legacy_job",
            )
            is None
        )

        assert (
            ensure_job_ai_quota_reserved_if_present(
                db,
                user_id=user_id,
                feature_key=FEATURE_CV_ANALYSIS,
                job_id=job_id,
            )
            is None
        )
    finally:
        db.close()
        _cleanup_user(user_id)


def test_quota_exhaustion_payload_has_paywall_contract():
    reset_at = datetime.now(timezone.utc)

    exc = AIQuotaExceededError(
        feature_key=FEATURE_CV_ANALYSIS,
        plan="free",
        limit=1,
        used=1,
        reserved=0,
        reset_at=reset_at,
    )

    payload = format_ai_quota_exceeded_payload(
        exc
    )

    error = payload["error"]
    details = error["details"]

    assert error["code"] == "AI_QUOTA_EXCEEDED"
    assert details["feature_key"] == FEATURE_CV_ANALYSIS
    assert details["plan"] == "free"
    assert details["limit"] == 1
    assert details["used"] == 1
    assert details["remaining"] == 0
    assert details["reset_at"] == reset_at.isoformat()


def test_async_execution_boundaries_are_wired():
    sources = {
        "profile": Path(
            "backend/app/api/v1/endpoints/profile.py"
        ).read_text(encoding="utf-8"),
        "applications": Path(
            "backend/app/api/v1/endpoints/applications.py"
        ).read_text(encoding="utf-8"),
        "cv_worker": Path(
            "worker/tasks/cv_extraction.py"
        ).read_text(encoding="utf-8"),
        "application_worker": Path(
            "worker/tasks/application_generation.py"
        ).read_text(encoding="utf-8"),
        "main": Path(
            "backend/app/main.py"
        ).read_text(encoding="utf-8"),
    }

    assert (
        "feature_key=FEATURE_CV_ANALYSIS"
        in sources["profile"]
    )
    assert (
        'reason="enqueue_failure"'
        in sources["profile"]
    )
    assert (
        'reason="user_cancelled"'
        in sources["profile"]
    )

    assert (
        "feature_key=FEATURE_APPLICATION_SUPPORT"
        in sources["applications"]
    )
    assert (
        'reason="enqueue_failure"'
        in sources["applications"]
    )

    assert (
        "settle_job_ai_quota_if_present("
        in sources["cv_worker"]
    )
    assert (
        'reason="worker_failure"'
        in sources["cv_worker"]
    )
    assert (
        "ensure_job_ai_quota_reserved_if_present("
        in sources["cv_worker"]
    )

    assert (
        "settle_job_ai_quota_if_present("
        in sources["application_worker"]
    )
    assert (
        'reason="worker_failure"'
        in sources["application_worker"]
    )
    assert (
        "ensure_job_ai_quota_reserved_if_present("
        in sources["application_worker"]
    )

    assert (
        "@app.exception_handler(AIQuotaExceededError)"
        in sources["main"]
    )
    assert "status_code=402" in sources["main"]
