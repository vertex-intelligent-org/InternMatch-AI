from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_social_sign_in_requires_existing_canonical_profile():
    source = _read("apps/mobile/src/screens/SignInScreen.js")

    assert "rejectMissingCanonicalAccount" in source
    assert source.count("const syncResult = await syncAuthenticatedUser();") >= 3
    assert source.count("if (!syncResult.has_profile)") >= 2
    assert "navigation.replace('Splash');" not in source
    assert "navigation.replace('OnboardingProfile');" not in source


def test_missing_social_account_is_deleted_not_left_as_orphan_auth_identity():
    sign_in = _read("apps/mobile/src/screens/SignInScreen.js")
    splash = _read("apps/mobile/src/screens/SplashScreen.js")

    assert "await deleteAccount();" in sign_in
    assert "await clearLocalSessionAfterAccountDeletion();" in sign_in

    assert "await deleteAccount();" in splash
    assert "await clearLocalSessionAfterAccountDeletion();" in splash


def test_confirmed_email_signup_uses_signup_only_server_endpoint():
    source = _read("apps/mobile/src/screens/SignInScreen.js")

    assert (
        "meta.account_type === 'intern' || meta.account_type === 'employer'"
        in source
    )
    assert "if (!metaName || !metaAccountType)" in source
    assert "await completeSignup({" in source
    assert "upsertProfile" not in source


def test_social_signup_requires_explicit_role_and_server_provisioning():
    source = _read("apps/mobile/src/screens/SignUpScreen.js")

    assert "useState(null); // null | 'intern' | 'employer'" in source
    assert "ensureAccountTypeSelected" in source
    assert "ensureSocialSignupReady" in source
    assert "completeSocialSignup" in source
    assert "await completeSignup({" in source
    assert "account_type: accountType" in source
    assert "upsertProfile" not in source
    assert "onboardingHints" not in source


def test_social_signup_does_not_write_role_into_apple_auth_metadata():
    source = _read("apps/mobile/src/screens/SignUpScreen.js")

    assert "const result = await signInWithApple();" in source
    assert "signInWithApple({" not in source


def test_existing_social_account_is_not_repurposed_by_signup():
    source = _read("apps/mobile/src/screens/SignUpScreen.js")

    assert "if (syncResult.has_profile)" in source
    assert "rejectExistingSignupAccount" in source
    assert "error instanceof ApiError && error.status === 409" in source


def test_splash_never_turns_orphan_session_into_signup():
    source = _read("apps/mobile/src/screens/SplashScreen.js")

    assert "onboardingHints" not in source
    assert "meta.account_type" not in source
    assert "initialAccountType" not in source
    assert "pendingDestinationRef.current = 'SignIn';" in source


def test_general_profile_endpoint_is_not_account_provisioning_endpoint():
    source = _read("backend/app/api/v1/endpoints/profile.py")

    assert "if existing_profile is None:" in source
    assert "status.HTTP_409_CONFLICT" in source
    assert "authenticated sign-up flow" in source


def test_backend_signup_endpoint_validates_supported_roles():
    source = _read("backend/app/api/v1/endpoints/auth.py")

    assert 'account_type: Literal["intern", "employer"]' in source
    assert '@router.post(' in source
    assert '"/complete-signup"' in source
    assert "status.HTTP_409_CONFLICT" in source


def test_provider_platform_contract_is_preserved():
    sign_in = _read("apps/mobile/src/screens/SignInScreen.js")
    sign_up = _read("apps/mobile/src/screens/SignUpScreen.js")
    apple_service = _read("apps/mobile/src/services/appleAuth.js")

    assert 'provider="google"' in sign_in
    assert 'provider="google"' in sign_up
    assert "Platform.OS === 'ios'" in sign_in
    assert "Platform.OS === 'ios'" in sign_up
    assert "Platform.OS !== 'ios'" in apple_service


def test_auth_messages_are_localized_in_all_supported_languages():
    required_keys = (
        "accountAlreadyExistsTitle:",
        "accountAlreadyExistsMessage:",
        "noAccountTitle:",
        "noAccountMessage:",
        "selectAccountType:",
    )

    for locale in ("en.js", "tr.js", "ar.js"):
        source = _read(f"apps/mobile/src/localization/locales/{locale}")
        for key in required_keys:
            assert key in source


def test_signup_role_has_no_implicit_student_default():
    source = _read("apps/mobile/src/screens/SignUpScreen.js")

    assert "const [accountType, setAccountType] = useState(null)" in source
    assert "if (!ensureAccountTypeSelected())" in source
