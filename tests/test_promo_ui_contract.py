from pathlib import Path

ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


def source(relative: str) -> str:
    return (
        ROOT
        / relative
    ).read_text(
        encoding="utf-8"
    )


def test_mobile_promo_panel_is_mounted():
    plans = source(
        "apps/mobile/src/screens/"
        "PlansScreen.js"
    )

    panel = source(
        "apps/mobile/src/components/"
        "PromoCodePanel.js"
    )

    api = source(
        "apps/mobile/src/services/api.ts"
    )

    assert "PromoCodePanel" in plans
    assert "redeemPromoCode" in panel
    assert "getPromoCodeStatus" in panel
    assert "'/promo-codes/redeem'" in api
    assert "'/promo-codes/status'" in api
    assert "setCode('')" in panel


def test_mobile_contains_no_promo_secrets():
    content = "\n".join(
        [
            source(
                "apps/mobile/src/services/api.ts"
            ),
            source(
                "apps/mobile/src/components/"
                "PromoCodePanel.js"
            ),
            source(
                "apps/mobile/src/screens/"
                "PlansScreen.js"
            ),
        ]
    )

    assert (
        "REVENUECAT_PROMO_SECRET_KEY"
        not in content
    )

    assert (
        "PROMO_CODE_HMAC_SECRET"
        not in content
    )


def test_admin_has_student_and_employer_management():
    page = source(
        "apps/admin/app/"
        "promo-codes/page.tsx"
    )

    assert (
        'renderAudience("student")'
        in page
    )

    assert (
        'renderAudience("employer")'
        in page
    )

    assert (
        "generatePrivateCode"
        in page
    )

    assert (
        "retireAdminPromoCampaign"
        in page
    )


def test_admin_types_do_not_expose_digest():
    content = source(
        "apps/admin/lib/types.ts"
    )

    assert "AdminPromoCampaign" in content
    assert "code_digest" not in content


def test_all_locales_contain_promo_copy():
    for locale in (
        "en",
        "tr",
        "ar",
    ):
        content = source(
            "apps/mobile/src/"
            "localization/locales/"
            f"{locale}.js"
        )

        assert "promo: {" in content
        assert "studentHint:" in content
        assert "employerHint:" in content
        assert "successMessage:" in content


def test_canonical_promo_routes_only():
    router = source(
        "backend/app/api/v1/router.py"
    )

    assert (
        router.count(
            "promo_codes.user_router"
        )
        == 1
    )

    assert (
        router.count(
            "promo_codes.admin_router"
        )
        == 1
    )

    assert 'prefix="/promo-codes"' in router

    assert (
        'prefix="/admin/promo-codes"'
        in router
    )

    assert "/me/promo" not in router

    assert (
        "/admin/promo-campaigns"
        not in router
    )



def test_promo_input_remains_visible_when_keyboard_opens():
    plans = source(
        "apps/mobile/src/screens/"
        "PlansScreen.js"
    )

    panel = source(
        "apps/mobile/src/components/"
        "PromoCodePanel.js"
    )

    assert "plansScrollRef" in plans
    assert "promoSectionYRef" in plans
    assert "handlePromoLayout" in plans
    assert "handlePromoInputFocus" in plans
    assert "scrollPromoIntoView" in plans

    assert (
        'keyboardShouldPersistTaps="handled"'
        in plans
    )

    assert (
        "automaticallyAdjustKeyboardInsets"
        in plans
    )

    assert "keyboardDismissMode={" in plans

    assert (
        "onInputFocus={"
        in plans
    )

    assert (
        "onFocus={onInputFocus}"
        in panel
    )

    # Keyboard accommodation must be dynamic.
    # Do not introduce permanent keyboard-sized
    # padding while the keyboard is closed.
    assert "keyboardHeight" not in plans
    assert "keyboardPadding" not in plans
