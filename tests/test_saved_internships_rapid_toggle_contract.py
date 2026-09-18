"""Rapid bookmark intent/session-isolation contract."""

import re
from pathlib import Path

ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

SOURCE = (
    ROOT
    / "apps/mobile/src/context/"
    "SavedInternshipsContext.js"
).read_text(
    encoding="utf-8"
)


def test_rapid_toggle_uses_synchronous_desired_state():
    assert (
        "desiredSavedStateRef = useRef(new Map())"
        in SOURCE
    )

    assert (
        "currentDesiredSaved ="
        in SOURCE
    )

    assert (
        "desiredSavedStateRef.current.get(id)"
        in SOURCE
    )

    assert (
        "desiredSavedStateRef.current.set("
        in SOURCE
    )

    assert (
        "const desiredSaved = !savedIds.has(id);"
        not in SOURCE
    )


def test_first_mutation_records_desired_state_immediately():
    assert (
        "const mutationToken = Symbol(id);"
        in SOURCE
    )

    assert (
        "desiredSavedStateRef.current.set("
        in SOURCE
    )

    assert (
        "!currentlySaved"
        in SOURCE
    )


def test_session_reset_clears_all_bookmark_mutation_state():
    assert (
        "queuedSavedStateRef.current.clear();"
        in SOURCE
    )

    assert (
        "desiredSavedStateRef.current.clear();"
        in SOURCE
    )

    assert (
        "mutationTokensRef.current.clear();"
        in SOURCE
    )


def test_old_async_mutation_cannot_unlock_new_session_mutation():
    combined_guard = re.compile(
        r"mutationTokensRef\.current\.get\(id\)"
        r"\s*!==\s*mutationToken"
        r"\s*\|\|\s*"
        r"currentUserIdRef\.current"
        r"\s*!==\s*activeUserId"
    )

    token_guard = re.compile(
        r"mutationTokensRef\.current\.get\(id\)"
        r"\s*!==\s*mutationToken"
    )

    # Exactly two async mutation paths exist:
    # save and unsave. Both must verify ownership
    # AND authenticated-user identity together.
    assert len(
        combined_guard.findall(SOURCE)
    ) == 2

    assert len(
        token_guard.findall(SOURCE)
    ) == 2


def test_save_and_unsave_paths_release_owned_state():
    assert SOURCE.count(
        "desiredSavedStateRef.current.delete(id);"
    ) == 2

    assert SOURCE.count(
        "mutationTokensRef.current.delete(id);"
    ) == 2

    assert SOURCE.count(
        "queuedSavedStateRef.current.delete(id);"
    ) >= 2
