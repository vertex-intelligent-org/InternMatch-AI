"""AI cancellation quota/refund contracts."""

from pathlib import Path

from app.services import (
    processing_job_cancellation as cancellation,
)

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (
        ROOT / path
    ).read_text(
        encoding="utf-8"
    )


def _block(
    text: str,
    start: str,
    end: str,
) -> str:
    start_index = text.index(start)
    end_index = text.index(
        end,
        start_index,
    )

    return text[
        start_index:end_index
    ]


def test_generic_cancel_feature_map_refunds_student_ai_features():
    mapping = (
        cancellation
        .CANCELLABLE_AI_JOB_QUOTA_FEATURES
    )

    assert (
        mapping["application_generation"]
        == "application_support"
    )

    assert (
        mapping["match_explanation"]
        == "match_explanation"
    )

    assert (
        mapping["interview_prep"]
        == "interview_prep"
    )


def test_generic_cancel_releases_before_commit():
    source = _read(
        "backend/app/services/"
        "processing_job_cancellation.py"
    )

    release_index = source.index(
        "release_job_ai_quota_if_present("
    )

    commit_index = source.index(
        "db.commit()",
        release_index,
    )

    assert release_index < commit_index

    assert (
        'reason="user_cancelled"'
        in source[
            release_index:commit_index
        ]
    )


def test_cover_letter_refreshes_usage_after_confirmed_cancel():
    source = _read(
        "apps/mobile/src/screens/"
        "CoverLetterDraftScreen.js"
    )

    block = _block(
        source,
        "const cancelled =",
        "if (leaveAfterCancellation)",
    )

    assert (
        "await cancelGeneration()"
        in block
    )

    assert (
        "if (!cancelled)"
        in block
    )

    assert (
        "refreshAIUsage().catch("
        in block
    )

    assert (
        block.index(
            "await cancelGeneration()"
        )
        <
        block.index(
            "refreshAIUsage().catch("
        )
    )


def test_cv_refreshes_usage_after_authoritative_cancel():
    source = _read(
        "apps/mobile/src/screens/"
        "CVUploadScreen.js"
    )

    block = _block(
        source,
        "await cancelCVAnalysis(activeJobId);",
        "if (leaveAfterCancellation)",
    )

    assert (
        "refreshAIUsageInBackground();"
        in block
    )

    assert (
        block.index(
            "await cancelCVAnalysis(activeJobId);"
        )
        <
        block.index(
            "refreshAIUsageInBackground();"
        )
    )


def test_why_you_match_refreshes_usage_after_cancel():
    source = _read(
        "apps/mobile/src/screens/"
        "WhyYouMatchScreen.js"
    )

    block = _block(
        source,
        "outcome.status ===\n"
        "                    'cancelled'",
        "outcome.status ===\n"
        "                    'failed'",
    )

    assert (
        "refreshAIUsage().catch("
        in block
    )


def test_interview_prep_refreshes_usage_after_cancel():
    source = _read(
        "apps/mobile/src/screens/"
        "ApplicationDetailScreen.js"
    )

    block = _block(
        source,
        "outcome.status ===\n"
        "                    'cancelled'",
        "outcome.status ===\n"
        "                    'failed'",
    )

    assert (
        "refreshAIUsage().catch("
        in block
    )


def test_cv_uses_specialized_cancel_endpoint():
    source = _read(
        "apps/mobile/src/screens/"
        "CVUploadScreen.js"
    )

    assert (
        "await cancelCVAnalysis(activeJobId)"
        in source
    )

    generic = _read(
        "backend/app/services/"
        "processing_job_cancellation.py"
    )

    assert (
        "CV extraction deliberately remains "
        "on its specialized cancellation endpoint"
        in generic
    )
