from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_shared_hook_uses_same_durable_job():
    source = _read(
        "apps/mobile/src/hooks/useCancellableAIJob.js"
    )

    assert "accepted?.job_id" in source
    assert "activeJobIdRef.current = jobId" in source
    assert "getProcessingJob(" in source
    assert "cancelProcessingJob(" in source
    assert "POLL_INTERVAL_MS" in source


def test_transient_failure_never_fakes_cancellation():
    source = _read(
        "apps/mobile/src/hooks/useCancellableAIJob.js"
    )

    assert (
        "Poll failure is not cancellation."
        in source
    )
    assert (
        "Keep polling the same authoritative job."
        in source
    )
    assert (
        "Never navigate as if cancellation succeeded."
        in source
    )


def test_terminal_race_contract_is_preserved():
    source = _read(
        "apps/mobile/src/hooks/useCancellableAIJob.js"
    )

    assert "authoritativeJob" in source
    assert "isCancelledJob" in source
    assert "isQuotaExceededJob" in source
    assert "AI_QUOTA_EXCEEDED" in source
    assert "'completed'" in source


def test_why_you_match_protects_back_and_stop():
    source = _read(
        "apps/mobile/src/screens/WhyYouMatchScreen.js"
    )

    assert "runExplanationJob(" in source
    assert "cancelExplanationJob()" in source
    assert (
        "requestExplanationCancellation"
        in source
    )
    assert (
        "onBackPress={handleProtectedBackPress}"
        in source
    )
    assert "'beforeRemove'" in source
    assert "event.preventDefault()" in source
    assert "aiCancellation.continue" in source
    assert "aiCancellation.cancel" in source


def test_interview_prep_protects_back_and_stop():
    source = _read(
        "apps/mobile/src/screens/ApplicationDetailScreen.js"
    )

    assert "runInterviewPrepJob(" in source
    assert "cancelInterviewPrepJob()" in source
    assert (
        "requestInterviewPrepCancellation"
        in source
    )
    assert (
        "onBackPress={handleProtectedApplicationBack}"
        in source
    )
    assert "'beforeRemove'" in source
    assert "event.preventDefault()" in source
    assert "interviewPrepCancelBtn" in source
    assert "aiCancellation.continue" in source
    assert "aiCancellation.cancel" in source


def test_existing_cancel_copy_exists_in_all_locales():
    for locale in ("en", "tr", "ar"):
        source = _read(
            f"apps/mobile/src/localization/locales/{locale}.js"
        )

        assert "aiCancellation:" in source
        assert "continue:" in source
        assert "cancel:" in source
        assert "cancelling:" in source
        assert "failedTitle:" in source
        assert "failedMessage:" in source
