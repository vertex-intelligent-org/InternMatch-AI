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



def test_confirmed_email_callback_bootstraps_profile_before_orphan_cleanup():
    source = _read("apps/mobile/src/screens/SplashScreen.js")
    root = _read("apps/mobile/src/navigation/RootNavigator.js")
    auth = _read("apps/mobile/src/services/auth.ts")

    # Cold-start and warm-app confirmation callbacks are both consumed.
    assert "Linking.getInitialURL()" in root
    assert "Linking.addEventListener('url'" in root
    assert "establishSessionFromAuthCallbackUrl" in root

    # The callback helper can persist a Supabase session from all supported
    # confirmation callback credential forms.
    assert "supabase.auth.verifyOtp" in auth
    assert "supabase.auth.setSession" in auth
    assert "supabase.auth.exchangeCodeForSession" in auth

    # Only an explicit email identity with sign-up metadata may bootstrap the
    # canonical account. Social orphan cleanup remains present and later.
    assert "EMAIL_CONFIRMATION_AUTO_BOOTSTRAP" in source
    assert "appMetadata.provider === 'email'" in source
    assert "providerList.includes('email')" in source
    assert "signupMetadata.full_name" in source
    assert "signupMetadata.account_type" in source
    assert "await completeSignup({" in source
    assert "const completedProfile = await refreshProfile();" in source
    assert "pendingDestinationRef.current = 'MainTabs';" in source
    assert "await deleteAccount();" in source

    bootstrap_index = source.index("EMAIL_CONFIRMATION_AUTO_BOOTSTRAP")
    complete_index = source.index("await completeSignup({", bootstrap_index)
    cleanup_index = source.index("await deleteAccount();", bootstrap_index)

    assert bootstrap_index < complete_index < cleanup_index


def test_store_social_signup_does_not_require_manual_identity_fields():
    signup = _read(
        "apps/mobile/src/screens/SignUpScreen.js"
    )

    google = _read(
        "apps/mobile/src/services/googleAuth.js"
    )

    apple = _read(
        "apps/mobile/src/services/appleAuth.js"
    )

    # Social signup must not require the
    # manual full-name/email/password form.
    ready_start = signup.index(
        "const ensureSocialSignupReady = () =>"
    )

    ready_end = signup.index(
        "const rejectExistingSignupAccount",
        ready_start,
    )

    ready = signup[
        ready_start:ready_end
    ]

    assert "ensureAccountTypeSelected()" in ready
    assert "fullName.trim()" not in ready

    # Google and Apple must pass the
    # provider-derived name into provisioning.
    google_start = signup.index(
        "const handleGoogle = async () =>"
    )

    apple_start = signup.index(
        "const handleApple = async () =>"
    )

    google_handler = signup[
        google_start:apple_start
    ]

    apple_handler = signup[
        apple_start:
    ]

    assert "result.fullName" in google_handler
    assert "result.fullName" in apple_handler

    # Preserve the original visual hierarchy:
    # manual signup first, social shortcuts below.
    manual_name = signup.index(
        "{/* Full Name */}"
    )

    primary_cta = signup.index(
        "onPress={handleCreateAccount}"
    )

    google_button = signup.index(
        'provider="google"'
    )

    apple_button = signup.index(
        "AppleAuthenticationButtonType"
    )

    assert manual_name < primary_cta
    assert primary_cta < google_button
    assert primary_cta < apple_button

    # Provider services expose a canonical name.
    assert "resolveGoogleFullName" in google
    assert "fullName:" in google

    assert "fullName: resolvedFullName" in apple

    assert (
        "AppleAuthenticationScope.FULL_NAME"
        in apple
    )

    assert (
        "AppleAuthenticationScope.EMAIL"
        in apple
    )
