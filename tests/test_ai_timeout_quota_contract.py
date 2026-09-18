"""Contracts for AI timeout quota safety."""

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


def test_application_timeout_reconciles_before_local_terminal_state():
    source = _read(
        "apps/mobile/src/hooks/"
        "useApplicationGeneration.js"
    )

    block = _block(
        source,
        "if (Date.now() - startTimeRef.current > TIMEOUT_MS)",
        "isPollingRef.current = true;",
    )

    assert (
        "await getProcessingJob("
        in block
    )

    assert (
        "await cancelProcessingJob("
        in block
    )

    assert (
        block.index(
            "await getProcessingJob("
        )
        <
        block.index(
            "await cancelProcessingJob("
        )
    )

    assert (
        "scheduleNextPoll();"
        in block
    )


def test_application_timeout_preserves_completed_race_result():
    source = _read(
        "apps/mobile/src/hooks/"
        "useApplicationGeneration.js"
    )

    block = _block(
        source,
        "if (Date.now() - startTimeRef.current > TIMEOUT_MS)",
        "isPollingRef.current = true;",
    )

    assert (
        "terminalJob?.status ==="
        in block
    )

    assert (
        "'completed'"
        in block
    )

    assert (
        "onComplete("
        in block
    )

    assert (
        "racedJob?.status ==="
        in block
    )


def test_cv_timeout_reconciles_and_cancels_authoritatively():
    source = _read(
        "apps/mobile/src/screens/"
        "CVUploadScreen.js"
    )

    block = _block(
        source,
        "if (Date.now() - startTimeRef.current > MAX_POLL_DURATION_MS)",
        "isPollingRef.current = true;",
    )

    assert (
        "await getProcessingJob("
        in block
    )

    assert (
        "await cancelCVAnalysis("
        in block
    )

    assert (
        block.index(
            "await getProcessingJob("
        )
        <
        block.index(
            "await cancelCVAnalysis("
        )
    )

    assert (
        "refreshAIUsageInBackground();"
        in block
    )


def test_cv_timeout_does_not_abandon_unproven_active_job():
    source = _read(
        "apps/mobile/src/screens/"
        "CVUploadScreen.js"
    )

    block = _block(
        source,
        "if (Date.now() - startTimeRef.current > MAX_POLL_DURATION_MS)",
        "isPollingRef.current = true;",
    )

    assert (
        "scheduleNextPoll(activeJobId);"
        in block
    )

    assert (
        "No terminal server proof"
        in block
    )


def test_match_and_interview_shared_hook_has_no_client_hard_timeout():
    source = _read(
        "apps/mobile/src/hooks/"
        "useCancellableAIJob.js"
    )

    assert "TIMEOUT_MS" not in source
    assert "MAX_POLL_DURATION_MS" not in source

    assert (
        "Keep polling the same authoritative job."
        in source
    )


def test_cv_completed_timeout_reconciliation_resets_clock_before_repoll():
    source = _read(
        "apps/mobile/src/screens/"
        "CVUploadScreen.js"
    )

    block = _block(
        source,
        "if (Date.now() - startTimeRef.current > MAX_POLL_DURATION_MS)",
        "isPollingRef.current = true;",
    )

    initial_completed = block[
        block.index(
            "terminalJob?.status ==="
        ):
        block.index(
            "terminalJob?.status ===\n"
            "        'failed'"
        )
    ]

    assert (
        "startTimeRef.current = Date.now();"
        in initial_completed
    )

    assert (
        initial_completed.index(
            "startTimeRef.current = Date.now();"
        )
        <
        initial_completed.index(
            "scheduleNextPoll(activeJobId);"
        )
    )

    race_start = block.index(
        "racedJob?.status ==="
    )

    race_failed = block.index(
        "racedJob?.status ===\n"
        "          'failed'",
        race_start,
    )

    raced_completed = block[
        race_start:race_failed
    ]

    assert (
        "startTimeRef.current = Date.now();"
        in raced_completed
    )

    assert (
        raced_completed.index(
            "startTimeRef.current = Date.now();"
        )
        <
        raced_completed.index(
            "scheduleNextPoll(activeJobId);"
        )
    )
