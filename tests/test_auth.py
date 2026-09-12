"""
Unit Tests for Supabase Bearer JWT Authentication Foundation & Auth Sync Endpoint.
Verifies token parsing, Supabase Auth verified claims integration,
claim validation, user_id extraction, and POST /api/v1/auth/sync.
All tests use opaque bearer tokens and mock Supabase client verified
claims with zero network calls.
"""

from typing import Optional
from uuid import UUID, uuid4

import pytest
from app.core.config import settings
from app.core.security import (
    AuthenticatedUser,
    get_current_user,
    get_current_user_id,
    verify_jwt_token,
)
from app.db.models import StudentProfile
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal

# FastAPI test router for temporary protected endpoints.
auth_test_router = APIRouter(prefix="/test-auth", tags=["Test Auth"])


@auth_test_router.get("/me")
def protected_me_endpoint(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Sample protected endpoint consuming get_current_user dependency."""
    return {
        "authenticated": True,
        "user_id": str(current_user.user_id),
        "email": current_user.email,
        "role": current_user.role,
    }


@auth_test_router.get("/user-id")
def protected_user_id_endpoint(
    user_id: UUID = Depends(get_current_user_id),
    client_supplied_user_id: Optional[str] = None,
):
    """
    Protected endpoint verifying that client-supplied user_id parameters
    cannot override the authenticated identity extracted from the JWT token.
    """
    return {
        "authenticated_user_id": str(user_id),
        "ignored_client_param": client_supplied_user_id,
    }


@pytest.fixture
def auth_test_client() -> TestClient:
    """Fixture providing TestClient with test auth routes mounted."""
    test_app = FastAPI()
    test_app.include_router(auth_test_router)
    return TestClient(test_app)


def test_valid_verified_claims_returns_authenticated_user(
    auth_test_client: TestClient, mock_supabase_auth
):
    """
    Test 1: Valid Supabase token with verified claims is accepted
    and extracts identity.
    """
    test_uuid = uuid4()
    token = "valid-token-alex"
    mock_supabase_auth(
        token,
        claims={
            "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
            "aud": "authenticated",
            "sub": str(test_uuid),
            "email": "alex.student@example.com",
            "role": "authenticated",
        },
    )

    response = auth_test_client.get("/test-auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["user_id"] == str(test_uuid)
    assert data["email"] == "alex.student@example.com"
    assert data["role"] == "authenticated"


def test_uuid_comes_from_verified_sub(auth_test_client: TestClient, mock_supabase_auth):
    """
    Test 2: Authenticated user_id UUID strictly derives from
    verified JWT sub claim.
    """
    authenticated_uuid = uuid4()
    attacker_supplied_uuid = str(uuid4())
    token = f"valid-user-{authenticated_uuid}"

    response = auth_test_client.get(
        f"/test-auth/user-id?client_supplied_user_id={attacker_supplied_uuid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated_user_id"] == str(authenticated_uuid)
    assert data["authenticated_user_id"] != attacker_supplied_uuid


def test_missing_authorization_header_returns_401(
    auth_test_client: TestClient,
):
    """Test 3: Missing Authorization header returns 401 UNAUTHORIZED."""
    response = auth_test_client.get("/test-auth/me")
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "UNAUTHORIZED"
    assert "Missing Authorization header" in data["detail"]["error"]["message"]


@pytest.mark.parametrize(
    "malformed_header",
    [
        "Basic dXNlcjpwYXNz",
        "Bearer",
        "Bearer   ",
        "Bearer token1 token2",
        "Token xyz123",
        "JWT xyz123",
    ],
)
def test_malformed_bearer_header_returns_401(auth_test_client: TestClient, malformed_header: str):
    """Test 4: Malformed Authorization header returns 401 UNAUTHORIZED."""
    response = auth_test_client.get("/test-auth/me", headers={"Authorization": malformed_header})
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "UNAUTHORIZED"
    assert "Invalid Authorization header format" in data["detail"]["error"]["message"]


def test_supabase_verification_rejection_returns_401(
    auth_test_client: TestClient, mock_supabase_auth
):
    """
    Test 5: Supabase claims verification failure returns 401
    without leaking secrets.
    """
    token = "rejected-secret-token"
    mock_supabase_auth(
        token,
        exc=RuntimeError("Supabase Auth error: Invalid signature with secret super_secret_val_999"),
    )

    response = auth_test_client.get("/test-auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "UNAUTHORIZED"
    assert "Invalid or expired authentication token." in data["detail"]["error"]["message"]
    # Secret protection
    assert "super_secret_val" not in response.text
    assert "secret" not in data["detail"]["error"]["message"].lower()


def test_empty_claims_response_returns_401(auth_test_client: TestClient, mock_supabase_auth):
    """Test 6: None or empty claims response returns 401 UNAUTHORIZED."""
    token = "empty-claims-token"
    mock_supabase_auth(token, claims=None)

    response = auth_test_client.get("/test-auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    data = response.json()
    assert "Invalid or expired authentication token." in data["detail"]["error"]["message"]


def test_wrong_issuer_returns_401(mock_supabase_auth):
    """Test 7: Token with wrong issuer returns 401 UNAUTHORIZED."""
    test_uuid = uuid4()
    token = "wrong-iss-token"
    mock_supabase_auth(
        token,
        claims={
            "iss": "https://malicious-auth-issuer.com/auth/v1",
            "aud": "authenticated",
            "sub": str(test_uuid),
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_jwt_token(token)
    assert exc_info.value.status_code == 401
    assert "Invalid JWT issuer." in exc_info.value.detail["error"]["message"]


def test_wrong_audience_returns_401(auth_test_client: TestClient, mock_supabase_auth):
    """
    Test 8: Token with wrong audience (e.g. 'anon') returns 401 UNAUTHORIZED.
    """
    test_uuid = uuid4()
    token = "wrong-aud-token"
    mock_supabase_auth(
        token,
        claims={
            "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
            "aud": "anon",
            "sub": str(test_uuid),
        },
    )

    response = auth_test_client.get("/test-auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    data = response.json()
    assert "audience" in data["detail"]["error"]["message"].lower()


def test_list_audience_containing_authenticated_is_accepted(
    auth_test_client: TestClient, mock_supabase_auth
):
    """Test 9: Token with list audience containing 'authenticated' is accepted."""
    test_uuid = uuid4()
    token = "list-aud-token"
    mock_supabase_auth(
        token,
        claims={
            "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
            "aud": ["authenticated", "other_aud"],
            "sub": str(test_uuid),
            "email": "test@example.com",
            "role": "authenticated",
        },
    )

    response = auth_test_client.get("/test-auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(test_uuid)


def test_missing_sub_returns_401(auth_test_client: TestClient, mock_supabase_auth):
    """Test 10: Token missing required 'sub' claim returns 401 UNAUTHORIZED."""
    token = "missing-sub-token"
    mock_supabase_auth(
        token,
        claims={
            "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
            "aud": "authenticated",
            "email": "nosub@example.com",
        },
    )

    response = auth_test_client.get("/test-auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    data = response.json()
    assert "sub" in data["detail"]["error"]["message"].lower()


def test_malformed_uuid_sub_returns_401(auth_test_client: TestClient, mock_supabase_auth):
    """Test 11: Token with non-UUID 'sub' claim returns 401 UNAUTHORIZED."""
    token = "bad-uuid-token"
    mock_supabase_auth(
        token,
        claims={
            "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
            "aud": "authenticated",
            "sub": "not-a-valid-uuid-format",
        },
    )

    response = auth_test_client.get("/test-auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    data = response.json()
    assert "valid uuid" in data["detail"]["error"]["message"].lower()


def test_optional_email_and_role_handling(auth_test_client: TestClient, mock_supabase_auth):
    """Test 12: Claims without optional email and role are handled gracefully."""
    test_uuid = uuid4()
    token = "minimal-token"
    mock_supabase_auth(
        token,
        claims={
            "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
            "aud": "authenticated",
            "sub": str(test_uuid),
        },
    )

    response = auth_test_client.get("/test-auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(test_uuid)
    assert data["email"] is None
    assert data["role"] is None


def test_get_current_user_id_dependency_unit():
    """Test 13: Direct unit test for get_current_user_id convenience dependency."""
    user_id = uuid4()
    auth_user = AuthenticatedUser(user_id=user_id, email="test@test.com", role="authenticated")
    import asyncio

    result = asyncio.run(get_current_user_id(current_user=auth_user))
    assert result == user_id


def test_missing_auth_configuration_returns_500(monkeypatch):
    """Test 14: Missing or placeholder Supabase auth settings returns 500."""
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    with pytest.raises(HTTPException) as exc_info:
        verify_jwt_token("some.token")
    assert exc_info.value.status_code == 500
    assert "Authentication service is not configured." in exc_info.value.detail["error"]["message"]

    monkeypatch.setattr(
        settings,
        "SUPABASE_URL",
        "https://placeholder-project.supabase.co",
    )
    monkeypatch.setattr(
        settings,
        "SUPABASE_PUBLISHABLE_KEY",
        "sb_pub_placeholder_key_client",
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_jwt_token("some.token")
    assert exc_info.value.status_code == 500

    monkeypatch.setattr(
        settings,
        "SUPABASE_URL",
        "https://legitimate-project.supabase.co",
    )
    monkeypatch.setattr(
        settings,
        "SUPABASE_PUBLISHABLE_KEY",
        "",
    )
    with pytest.raises(HTTPException) as exc_info:
        verify_jwt_token("some.token")
    assert exc_info.value.status_code == 500


# --- Gate 2.10.1: POST /api/v1/auth/sync Endpoint Tests ---


def test_post_auth_sync_valid_jwt_without_profile(client: TestClient, mock_supabase_auth):
    """
    Test 15: POST /api/v1/auth/sync returns 200 OK with has_profile=False
    when profile absent.
    """
    user_uuid = uuid4()
    token = f"valid-user-{user_uuid}"

    response = client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user_uuid)
    assert data["email"] == "student@example.com"
    assert data["has_profile"] is False


def test_post_auth_sync_valid_jwt_with_profile(client: TestClient, mock_supabase_auth):
    """
    Test 16: POST /api/v1/auth/sync returns 200 OK with has_profile=True
    when profile exists.
    """
    user_uuid = uuid4()

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(user_id=user_uuid, full_name="Synced Student")
        db.add(profile)
        db.commit()
    finally:
        db.close()

    token = f"valid-user-{user_uuid}"
    response = client.post("/api/v1/auth/sync", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user_uuid)
    assert data["email"] == "student@example.com"
    assert data["has_profile"] is True


def test_post_auth_sync_missing_header_returns_401(client: TestClient):
    """Test 17: POST /api/v1/auth/sync without Authorization header returns 401 UNAUTHORIZED."""
    response = client.post("/api/v1/auth/sync")
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_post_auth_sync_invalid_token_returns_401(client: TestClient, mock_supabase_auth):
    """Test 18: POST /api/v1/auth/sync with invalid JWT returns 401 UNAUTHORIZED."""
    mock_supabase_auth("invalid.token.value", exc=RuntimeError("Invalid token"))
    response = client.post(
        "/api/v1/auth/sync", headers={"Authorization": "Bearer invalid.token.value"}
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_post_auth_sync_ignores_client_body_or_query_overrides(
    client: TestClient, mock_supabase_auth
):
    """Test 19: POST /api/v1/auth/sync ignores client payload identity override attempts."""
    authenticated_uuid = uuid4()
    attacker_uuid = uuid4()
    token = f"valid-user-{authenticated_uuid}"

    malicious_payload = {
        "user_id": str(attacker_uuid),
        "email": "attacker@evil.com",
    }
    response = client.post(
        f"/api/v1/auth/sync?user_id={attacker_uuid}",
        json=malicious_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(authenticated_uuid)
    assert data["user_id"] != str(attacker_uuid)
    assert data["email"] == "student@example.com"

def test_verify_jwt_reuses_supabase_client_for_same_configuration(monkeypatch):
    """Repeated JWT verification reuses the client but never caches token claims."""
    import app.core.security as security_module

    user_id = uuid4()
    create_calls = []
    claims_calls = []

    class FakeAuth:
        def get_claims(self, *, jwt):
            claims_calls.append(jwt)
            return {
                "claims": {
                    "iss": (
                        f"{security_module.settings.SUPABASE_URL.rstrip('/')}"
                        "/auth/v1"
                    ),
                    "aud": "authenticated",
                    "sub": str(user_id),
                }
            }

    class FakeClient:
        def __init__(self):
            self.auth = FakeAuth()

    fake_client = FakeClient()

    def fake_create_client(url, key):
        create_calls.append((url, key))
        return fake_client

    monkeypatch.setattr(
        security_module,
        "create_client",
        fake_create_client,
    )

    security_module._get_supabase_auth_client.cache_clear()

    try:
        first = security_module.verify_jwt_token(
            "first.jwt.token"
        )
        second = security_module.verify_jwt_token(
            "second.jwt.token"
        )

        assert first["sub"] == str(user_id)
        assert second["sub"] == str(user_id)

        assert len(create_calls) == 1

        assert claims_calls == [
            "first.jwt.token",
            "second.jwt.token",
        ]
    finally:
        security_module._get_supabase_auth_client.cache_clear()


# --- Gate 1: canonical role-aware signup provisioning ---


def test_complete_signup_creates_canonical_employer_profile(
    client: TestClient,
    mock_supabase_auth,
):
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    response = client.post(
        "/api/v1/auth/complete-signup",
        json={
            "full_name": "Acme Recruiter",
            "department": "Talent",
            "account_type": "employer",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["created"] is True
    assert data["user_id"] == str(user_id)
    assert data["account_type"] == "employer"

    db = TestingSessionLocal()
    try:
        profile = (
            db.query(StudentProfile)
            .filter(StudentProfile.user_id == user_id)
            .one()
        )
        assert profile.full_name == "Acme Recruiter"
        assert profile.preferences["account_type"] == "employer"
        assert profile.preferences["department"] == "Talent"
    finally:
        db.close()


def test_complete_signup_rejects_duplicate_profile_without_role_mutation(
    client: TestClient,
    mock_supabase_auth,
):
    user_id = uuid4()

    db = TestingSessionLocal()
    try:
        db.add(
            StudentProfile(
                user_id=user_id,
                full_name="Existing Student",
                preferences={"account_type": "intern"},
            )
        )
        db.commit()
    finally:
        db.close()

    token = f"valid-user-{user_id}"
    response = client.post(
        "/api/v1/auth/complete-signup",
        json={
            "full_name": "Attempted Employer",
            "department": "HR",
            "account_type": "employer",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409

    db = TestingSessionLocal()
    try:
        profile = (
            db.query(StudentProfile)
            .filter(StudentProfile.user_id == user_id)
            .one()
        )
        assert profile.full_name == "Existing Student"
        assert profile.preferences["account_type"] == "intern"
    finally:
        db.close()


def test_complete_signup_rejects_unsupported_role(
    client: TestClient,
    mock_supabase_auth,
):
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    response = client.post(
        "/api/v1/auth/complete-signup",
        json={
            "full_name": "Role Injection",
            "department": "Security",
            "account_type": "admin",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422

    db = TestingSessionLocal()
    try:
        profile = (
            db.query(StudentProfile)
            .filter(StudentProfile.user_id == user_id)
            .one_or_none()
        )
        assert profile is None
    finally:
        db.close()


def test_complete_signup_requires_authentication(client: TestClient):
    response = client.post(
        "/api/v1/auth/complete-signup",
        json={
            "full_name": "Anonymous User",
            "department": None,
            "account_type": "intern",
        },
    )

    assert response.status_code == 401
