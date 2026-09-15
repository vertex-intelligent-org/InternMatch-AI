from pathlib import Path

PAGE = Path(
    "apps/landing/pages/data-deletion.js"
)


def _source() -> str:
    return PAGE.read_text(
        encoding="utf-8"
    )


def _normalized_source() -> str:
    """
    Normalize source whitespace so JSX line wrapping does not make
    user-visible prose contract tests formatting-sensitive.
    """
    return " ".join(
        _source().split()
    )


def test_public_account_deletion_resource_exists():
    assert PAGE.exists()

    source = _normalized_source()

    assert "InternMatch AI" in source
    assert "VERTEX AI" in source
    assert "Delete your InternMatch AI account" in source


def test_web_resource_allows_external_deletion_request():
    source = _normalized_source()

    assert (
        "mailto:internmatch@vertexintelligent.com"
        in source
    )

    assert (
        "Request account deletion"
        in source
    )

    assert (
        "If you no longer have the app"
        in source
    )

    assert (
        "cannot access"
        in source
    )


def test_web_resource_does_not_require_app_reinstallation():
    source = _normalized_source()

    assert (
        "Request deletion without the app"
        in source
    )

    assert (
        "download the app"
        not in source.lower()
    )

    assert (
        "reinstall"
        not in source.lower()
    )


def test_web_resource_explains_account_and_data_deletion():
    source = _normalized_source()

    assert (
        "permanently delete"
        in source.lower()
    )

    assert (
        "associated product data"
        in source.lower()
    )

    assert (
        "temporarily disabling"
        in source.lower()
    )


def test_web_resource_discloses_limited_retention():
    source = _normalized_source()

    assert "security" in source.lower()
    assert "fraud prevention" in source.lower()
    assert "regulatory" in source.lower()
    assert "legal obligations" in source.lower()


def test_web_resource_explains_store_subscription_boundary():
    source = _normalized_source()

    assert "Apple App Store" in source
    assert "Google Play" in source

    assert (
        "does not automatically cancel"
        in source
    )

    assert (
        "managed separately"
        in source
    )


def test_web_resource_never_requests_sensitive_credentials():
    source = _normalized_source()

    assert (
        "Never send your password"
        in source
    )

    assert (
        "authentication codes"
        in source
    )

    assert (
        "identity documents"
        in source
    )
