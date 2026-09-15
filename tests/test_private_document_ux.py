from uuid import uuid4

from fastapi.testclient import TestClient


def test_private_avatar_api_keeps_machine_readable_401(
    client: TestClient,
):
    response = client.get(
        "/api/v1/profile/avatar/content"
    )

    assert response.status_code == 401

    assert (
        "application/json"
        in response.headers["content-type"]
    )


def test_private_avatar_browser_redirects_to_generic_page(
    client: TestClient,
):
    response = client.get(
        "/api/v1/profile/avatar/content",
        headers={
            "Accept": "text/html",
            "Accept-Language": "en",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    assert (
        response.headers["location"]
        == "/document-unavailable"
    )


def test_private_cv_browser_redirect_hides_all_resource_ids(
    client: TestClient,
):
    internship_id = str(
        uuid4()
    )

    application_id = str(
        uuid4()
    )

    response = client.get(
        (
            f"/api/v1/internships/{internship_id}"
            f"/applicants/{application_id}"
            f"/cv/content"
        ),
        headers={
            "Accept": "text/html",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    location = (
        response.headers["location"]
    )

    assert (
        location
        == "/document-unavailable"
    )

    assert internship_id not in location
    assert application_id not in location

    assert (
        "supabase"
        not in location.lower()
    )


def test_private_document_page_english(
    client: TestClient,
):
    response = client.get(
        "/document-unavailable?lang=en"
    )

    assert response.status_code == 200

    assert (
        "text/html"
        in response.headers["content-type"]
    )

    assert 'lang="en"' in response.text
    assert "Document unavailable" in response.text
    assert "InternMatch AI" in response.text

    assert (
        "supabase"
        not in response.text.lower()
    )

    assert (
        response.headers["cache-control"]
        == "private, no-store, max-age=0"
    )


def test_private_document_page_arabic(
    client: TestClient,
):
    response = client.get(
        "/document-unavailable?lang=ar"
    )

    assert response.status_code == 200
    assert 'lang="ar"' in response.text
    assert 'dir="rtl"' in response.text
    assert "تعذر فتح المستند" in response.text


def test_private_document_page_turkish(
    client: TestClient,
):
    response = client.get(
        "/document-unavailable?lang=tr"
    )

    assert response.status_code == 200
    assert 'lang="tr"' in response.text
    assert "Belge açılamıyor" in response.text


def test_private_document_page_language_detection(
    client: TestClient,
):
    response = client.get(
        "/document-unavailable",
        headers={
            "Accept-Language":
                "ar-SA,ar;q=0.9,en;q=0.8",
        },
    )

    assert response.status_code == 200
    assert 'lang="ar"' in response.text


def _compliance_content_runtime_cases():
    claim_id = (
        "11111111-1111-4111-8111-111111111111"
    )
    evidence_id = (
        "22222222-2222-4222-8222-222222222222"
    )

    cases = (
        (
            "employer",
            (
                "/api/v1/employer-compliance/"
                f"claims/{claim_id}/evidence/"
                f"{evidence_id}/content"
            ),
        ),
        (
            "admin",
            (
                "/api/v1/admin/employer-compliance/"
                f"claims/{claim_id}/evidence/"
                f"{evidence_id}/content"
            ),
        ),
    )

    return cases, claim_id, evidence_id


def test_compliance_content_routes_are_registered_and_keep_api_denials_machine_readable():
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    cases, claim_id, evidence_id = (
        _compliance_content_runtime_cases()
    )

    for route_role, request_path in cases:
        response = client.get(
            request_path,
            headers={
                "Accept": "application/json",
            },
            follow_redirects=False,
        )

        # Exact 401 is intentional:
        # a missing/unregistered route would return 404.
        assert response.status_code == 401, (
            route_role,
            request_path,
            response.status_code,
            response.text,
        )

        assert response.headers.get(
            "location"
        ) is None

        assert (
            "application/json"
            in response.headers.get(
                "content-type",
                "",
            ).lower()
        )

        body = response.content.lower()

        assert b"supabase.co" not in body
        assert claim_id.encode() not in body
        assert evidence_id.encode() not in body


def test_compliance_content_browser_denials_redirect_to_generic_branded_page():
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    cases, claim_id, evidence_id = (
        _compliance_content_runtime_cases()
    )

    for route_role, request_path in cases:
        response = client.get(
            request_path,
            headers={
                "Accept": "text/html",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303, (
            route_role,
            request_path,
            response.status_code,
            response.text,
        )

        location = response.headers.get(
            "location",
            "",
        )

        assert location == "/document-unavailable"

        normalized_location = location.lower()

        assert claim_id not in normalized_location
        assert evidence_id not in normalized_location
        assert "supabase.co" not in normalized_location
        assert "storage" not in normalized_location

        assert (
            response.headers.get(
                "cache-control"
            )
            == "private, no-store, max-age=0"
        )

        assert (
            response.headers.get(
                "pragma"
            )
            == "no-cache"
        )

        assert (
            response.headers.get(
                "referrer-policy"
            )
            == "no-referrer"
        )

        assert (
            response.headers.get(
                "x-content-type-options"
            )
            == "nosniff"
        )
