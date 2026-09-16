"""Request correlation and safe operational logging contracts."""

import re
from unittest.mock import patch

from fastapi.testclient import TestClient

_REQUEST_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def test_request_id_is_server_generated(
    client: TestClient,
):
    response = client.get(
        "/health",
        headers={
            "X-Request-ID": "attacker-controlled-id",
        },
    )

    assert response.status_code == 200

    request_id = response.headers["X-Request-ID"]

    assert _REQUEST_ID_PATTERN.fullmatch(
        request_id
    )
    assert request_id != "attacker-controlled-id"


def test_request_ids_are_unique(
    client: TestClient,
):
    first = client.get("/health")
    second = client.get("/health")

    assert first.status_code == 200
    assert second.status_code == 200

    first_id = first.headers["X-Request-ID"]
    second_id = second.headers["X-Request-ID"]

    assert _REQUEST_ID_PATTERN.fullmatch(
        first_id
    )
    assert _REQUEST_ID_PATTERN.fullmatch(
        second_id
    )
    assert first_id != second_id


def test_request_id_is_present_on_not_found_response(
    client: TestClient,
):
    response = client.get(
        "/definitely-not-a-real-route"
    )

    assert response.status_code == 404

    request_id = response.headers[
        "X-Request-ID"
    ]

    assert _REQUEST_ID_PATTERN.fullmatch(
        request_id
    )


def test_completion_log_uses_path_not_query_string(
    client: TestClient,
):
    secret_query_value = (
        "do-not-write-this-query-value-to-logs"
    )

    with patch(
        "app.main.logger.info"
    ) as mock_info:
        response = client.get(
            "/health",
            params={
                "debug_token": secret_query_value,
            },
        )

    assert response.status_code == 200

    request_id = response.headers[
        "X-Request-ID"
    ]

    matching_calls = [
        call
        for call in mock_info.call_args_list
        if call.args
        and call.args[0].startswith(
            "request_completed "
        )
    ]

    assert len(matching_calls) == 1

    call = matching_calls[0]

    assert request_id in call.args
    assert "GET" in call.args
    assert "/health" in call.args

    rendered_call = repr(call)

    assert secret_query_value not in rendered_call
    assert "debug_token" not in rendered_call
