from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PLANS_SCREEN = (
    ROOT
    / "apps"
    / "mobile"
    / "src"
    / "screens"
    / "PlansScreen.js"
)


def test_plans_refreshes_authoritative_ai_usage_on_focus():
    source = PLANS_SCREEN.read_text(
        encoding="utf-8"
    )

    assert (
        "useFocusEffect"
        in source
    )

    assert (
        "refreshAIUsage,"
        in source
    )

    assert (
        "refreshAIUsage().catch("
        in source
    )

    assert (
        "AI usage refresh on Plans focus failed:"
        in source
    )

    assert (
        "if (isEmployer)"
        in source
    )


def test_plans_does_not_mutate_quota_locally():
    source = PLANS_SCREEN.read_text(
        encoding="utf-8"
    )

    assert "setAIUsage(" not in source
    assert "used_count" not in source
    assert "reserved_count" not in source
