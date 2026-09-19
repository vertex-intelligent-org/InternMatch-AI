from pathlib import Path

ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


def source(relative: str) -> str:
    return (
        ROOT / relative
    ).read_text(
        encoding="utf-8"
    )


def test_opportunity_card_text_is_width_safe():
    screen = source(
        "apps/mobile/src/screens/"
        "EmployerOpportunitiesScreen.js"
    )

    assert 'ellipsizeMode="tail"' in screen
    assert "styles.summaryMetaText" in screen

    assert "flexShrink: 1" in screen
    assert "minWidth: 0" in screen

    assert "pendingReviewText" in screen

    assert (
        "Waiting for InternMatch team approval"
        in screen
    )


def test_opportunity_card_opens_full_detail_screen():
    screen = source(
        "apps/mobile/src/screens/"
        "EmployerOpportunitiesScreen.js"
    )

    navigator = source(
        "apps/mobile/src/navigation/"
        "RootNavigator.js"
    )

    detail = source(
        "apps/mobile/src/screens/"
        "EmployerOpportunityDetailScreen.js"
    )

    assert (
        "handleOpenOpportunityDetails"
        in screen
    )

    assert (
        "'EmployerOpportunityDetail'"
        in screen
    )

    assert (
        'name="EmployerOpportunityDetail"'
        in navigator
    )

    assert (
        "EmployerOpportunityDetailScreen"
        in navigator
    )

    assert (
        "getEmployerInternshipDetail"
        in detail
    )

    assert (
        "detail.description"
        in detail
    )

    assert (
        "detail.required_skills"
        in detail
    )

    assert (
        "detail.preferred_skills"
        in detail
    )


def test_detail_screen_is_localized():
    for locale in (
        "en",
        "tr",
        "ar",
    ):
        content = source(
            "apps/mobile/src/localization/"
            f"locales/{locale}.js"
        )

        assert "detailsTitle:" in content
        assert "detailsLoadError:" in content
