"""Mobile UI/UX regression contracts for September polish."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (
        ROOT / path
    ).read_text(
        encoding="utf-8"
    )


def test_employer_opportunities_header_uses_card_text_rail():
    source = _read(
        "apps/mobile/src/screens/"
        "EmployerOpportunitiesScreen.js"
    )

    assert (
        "headerTitleBlock: {\n"
        "    flex: 1,\n"
        "    marginEnd: spacing.sm,\n"
        "    paddingStart: spacing.md,"
        in source
    )


def test_create_opportunity_ai_assistant_has_separation():
    source = _read(
        "apps/mobile/src/screens/"
        "CreateOpportunityScreen.js"
    )

    assert (
        "<View style={styles.aiAssistantSection}>"
        in source
    )

    assert (
        "aiAssistantSection: {\n"
        "    marginTop: spacing.lg,"
        in source
    )


def test_bookmark_second_tap_is_not_dropped_while_mutating():
    source = _read(
        "apps/mobile/src/context/"
        "SavedInternshipsContext.js"
    )

    assert (
        "queuedSavedStateRef = useRef(new Map())"
        in source
    )

    guard_start = source.index(
        "if (mutatingIdsRef.current.has(id))"
    )

    guard_end = source.index(
        "if (!currentUserIdRef.current)",
        guard_start,
    )

    guard = source[
        guard_start:guard_end
    ]

    assert "return;" in guard
    assert (
        "queuedSavedStateRef.current.set("
        in guard
    )
    assert (
        "setSavedIds((prev) =>"
        in guard
    )


def test_bookmark_queue_serializes_latest_server_intent():
    source = _read(
        "apps/mobile/src/context/"
        "SavedInternshipsContext.js"
    )

    assert (
        "while (\n"
        "            queuedSavedStateRef.current.has(id)"
        in source
    )

    assert "await saveInternship(id);" in source
    assert "await unsaveInternship(id);" in source

    assert (
        "Bookmark reconciliation refresh failed:"
        in source
    )


def test_bookmark_buttons_remain_pressable_during_reconciliation():
    internships = _read(
        "apps/mobile/src/screens/"
        "InternshipsScreen.js"
    )

    detail = _read(
        "apps/mobile/src/screens/"
        "InternshipDetailScreen.js"
    )

    assert (
        "disabled={isMutating(item.id)}"
        not in internships
    )

    assert (
        "disabled={!internship || "
        "isMutating(internshipId)}"
        not in detail
    )

    assert (
        "disabled={!internship}"
        in detail
    )


def test_js_splash_is_solid_brand_color_without_gradient():
    source = _read(
        "apps/mobile/src/screens/"
        "SplashScreen.js"
    )

    assert "LinearGradient" not in source
    assert "gradientColors" not in source

    assert (
        "backgroundColor:\n"
        "            colors.accentStrong"
        in source
    )

    # Animation itself must remain intact.
    assert "<SplashBowArrowAnimation" in source
    assert "onAnimationComplete={handleAnimationComplete}" in source
    assert "onTargetImpact={handleTargetImpact}" in source


def test_native_splash_matches_accent_strong_color():
    app = json.loads(
        _read("apps/mobile/app.json")
    )

    splash = next(
        plugin
        for plugin in app["expo"]["plugins"]
        if (
            isinstance(plugin, list)
            and plugin[0]
            == "expo-splash-screen"
        )
    )

    assert (
        splash[1]["backgroundColor"]
        == "#0B5F70"
    )
