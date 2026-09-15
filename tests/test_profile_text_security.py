import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.profile import (
    StudentProfileCreateUpdate,
)
from app.services.profile_text_security import (
    looks_like_sensitive_credential,
    normalize_public_profile_headline,
    sanitize_extracted_profile_headline,
)


@pytest.mark.parametrize(
    "headline",
    [
        "Software Engineering Student",
        "Backend Developer",
        "C++ Developer",
        "AI & Machine Learning Student",
        "Full-Stack Engineer",
        "Computer Engineering Student | Python",
    ],
)
def test_normal_professional_headlines_are_allowed(
    headline,
):
    assert (
        normalize_public_profile_headline(
            headline
        )
        == headline
    )


@pytest.mark.parametrize(
    "secret",
    [
        "MyPassword2026!",
        "password=SuperSecret123!",
        "pwd:ExampleSecret123!",
        "Bearer abcdefghijklmnopqrstuvwxyz",
        (
            "eyJhbGciOiJIUzI1NiJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "abcdefghijklmnop"
        ),
        "sk-abcdefghijklmnopqrstuvwxyz123456",
        "ghp_abcdefghijklmnopqrstuvwxyz123456",
    ],
)
def test_credential_like_headlines_are_detected(
    secret,
):
    assert (
        looks_like_sensitive_credential(
            secret
        )
        is True
    )


def test_manual_profile_payload_rejects_password_like_headline():
    with pytest.raises(
        ValidationError
    ):
        StudentProfileCreateUpdate(
            full_name="Security Candidate",
            headline="MyPassword2026!",
            preferences={},
        )


def test_manual_profile_payload_normalizes_safe_headline():
    payload = StudentProfileCreateUpdate(
        full_name="Security Candidate",
        headline=(
            "  Backend   Engineering "
            " Student  "
        ),
        preferences={},
    )

    assert (
        payload.headline
        == "Backend Engineering Student"
    )


@pytest.mark.parametrize(
    "secret",
    [
        "MyPassword2026!",
        "password=SuperSecret123!",
        "sk-abcdefghijklmnopqrstuvwxyz123456",
    ],
)
def test_cv_extraction_drops_credential_like_headline(
    secret,
):
    assert (
        sanitize_extracted_profile_headline(
            secret
        )
        is None
    )


def test_cv_extraction_preserves_safe_professional_headline():
    assert (
        sanitize_extracted_profile_headline(
            "  Junior   Backend Engineer  "
        )
        == "Junior Backend Engineer"
    )
