"""Contract tests for immediate AI paywall routing."""

from pathlib import Path


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


def _assert_before(
    text: str,
    first: str,
    second: str,
) -> None:
    first_index = text.find(first)
    second_index = text.find(second)

    assert first_index >= 0, first
    assert second_index >= 0, second
    assert first_index < second_index


def test_shared_student_quota_gate_exists():
    provider = _read(
        "apps/mobile/src/context/"
        "SubscriptionProvider.js"
    )

    assert (
        "const checkAIQuotaAvailable = useCallback"
        in provider
    )

    assert (
        "await refreshAIUsage()"
        in provider
    )

    assert (
        "checkAIQuotaAvailable,"
        in provider
    )

    gate = _block(
        provider,
        "const checkAIQuotaAvailable",
        "const reconcileSubscription",
    )

    _assert_before(
        gate,
        "cachedFeature?.remaining === 0",
        "await refreshAIUsage()",
    )


def test_cv_checks_quota_before_document_picker():
    text = _read(
        "apps/mobile/src/screens/"
        "CVUploadScreen.js"
    )

    block = _block(
        text,
        "const pickFileAndUpload",
        "const startUploadAndPolling",
    )

    _assert_before(
        block,
        "checkAIQuotaAvailable(",
        "DocumentPicker.getDocumentAsync(",
    )

    assert (
        "navigation.navigate('Plans')"
        in block
    )


def test_application_support_checks_before_generation():
    text = _read(
        "apps/mobile/src/screens/"
        "CoverLetterDraftScreen.js"
    )

    block = _block(
        text,
        "const handleGenerate = async",
        "const handleDiscardDraft",
    )

    _assert_before(
        block,
        "checkAIQuotaAvailable(",
        "startGeneration(",
    )

    assert (
        "navigation.navigate('Plans')"
        in block
    )


def test_match_explanation_checks_before_enqueue():
    text = _read(
        "apps/mobile/src/screens/"
        "WhyYouMatchScreen.js"
    )

    block = _block(
        text,
        "const fetchExplanationData",
        "const leaveWhyYouMatch",
    )

    _assert_before(
        block,
        "checkAIQuotaAvailable(",
        "runExplanationJob(",
    )

    assert "'Plans'" in block


def test_interview_prep_checks_before_enqueue():
    text = _read(
        "apps/mobile/src/screens/"
        "ApplicationDetailScreen.js"
    )

    block = _block(
        text,
        "const handleGenerateInterviewPrep",
        "const leaveApplicationDetail",
    )

    _assert_before(
        block,
        "checkAIQuotaAvailable(",
        "runInterviewPrepJob(",
    )

    assert (
        "interviewPrepActionInFlightRef.current"
        in block
    )

    assert (
        "navigation.navigate('Plans')"
        in block
    )


def test_student_backend_quota_fallbacks_remain():
    paths = (
        "apps/mobile/src/screens/"
        "CVUploadScreen.js",

        "apps/mobile/src/screens/"
        "CoverLetterDraftScreen.js",

        "apps/mobile/src/screens/"
        "WhyYouMatchScreen.js",

        "apps/mobile/src/screens/"
        "ApplicationDetailScreen.js",
    )

    for path in paths:
        text = _read(path)

        assert (
            "AI_QUOTA_EXCEEDED"
            in text
        )

        assert (
            "Plans"
            in text
        )


def test_employer_candidate_free_quota_routes_to_plans():
    text = _read(
        "apps/mobile/src/components/"
        "EmployerCandidateIntelligence.js"
    )

    insight = _block(
        text,
        "async function handleGenerateInsight",
        "async function handleGenerateInterviewKit",
    )

    assert (
        "error.code === 'AI_QUOTA_EXCEEDED'"
        in insight
    )

    assert (
        "currentPolicy?.is_pro !== true"
        in insight
    )

    assert (
        "navigation.navigate('Plans')"
        in insight
    )


def test_employer_pro_only_ai_routes_directly():
    candidate = _read(
        "apps/mobile/src/components/"
        "EmployerCandidateIntelligence.js"
    )

    description = _read(
        "apps/mobile/src/components/"
        "EmployerDescriptionAssistant.js"
    )

    shortlist = _read(
        "apps/mobile/src/components/"
        "EmployerShortlistComparison.js"
    )

    assert (
        "if (!nextPolicy.interview_kit_available)"
        in candidate
    )

    assert (
        "navigation.navigate('Plans')"
        in candidate
    )

    assert (
        "if (!policy.internship_description_available)"
        in description
    )

    assert (
        "navigation.navigate('Plans')"
        in description
    )

    assert (
        "if (!policy.shortlist_comparison_available)"
        in shortlist
    )

    assert (
        "navigation.navigate('Plans')"
        in shortlist
    )
