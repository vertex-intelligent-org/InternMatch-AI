"""Server-only RevenueCat promotional entitlement grant client."""

import json
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
from uuid import UUID

from app.core.config import settings

REVENUECAT_V2_BASE_URL = "https://api.revenuecat.com/v2"
MAX_ENTITLEMENT_PAGES = 10


class RevenueCatPromoConfigurationError(RuntimeError):
    """Promotional grant credentials or RevenueCat resources are invalid."""


class RevenueCatPromoProviderError(RuntimeError):
    """RevenueCat promotional grant could not be completed."""


def _credentials() -> tuple[str, str]:
    api_key = (
        settings.REVENUECAT_PROMO_SECRET_KEY
        or ""
    ).strip()

    project_id = (
        settings.REVENUECAT_PROJECT_ID
        or ""
    ).strip()

    if not api_key:
        raise RevenueCatPromoConfigurationError(
            "RevenueCat promotional grant key is not configured."
        )

    if not project_id:
        raise RevenueCatPromoConfigurationError(
            "RevenueCat project ID is not configured."
        )

    return api_key, project_id


def _validate_url(url: str) -> None:
    parsed = urlparse(url)

    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.revenuecat.com"
    ):
        raise RevenueCatPromoProviderError(
            "RevenueCat returned an unexpected URL."
        )


def _request_json(
    *,
    url: str,
    method: str,
    api_key: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_url(url)

    encoded_body = (
        json.dumps(body).encode("utf-8")
        if body is not None
        else None
    )

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    if encoded_body is not None:
        headers["Content-Type"] = "application/json"

    request = Request(
        url,
        headers=headers,
        data=encoded_body,
        method=method,
    )

    try:
        with urlopen(
            request,
            timeout=8,
        ) as response:
            raw = response.read()
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise RevenueCatPromoConfigurationError(
                "RevenueCat rejected promotional-grant credentials "
                "or required API permissions are missing."
            ) from exc

        raise RevenueCatPromoProviderError(
            f"RevenueCat promotional grant returned HTTP {exc.code}."
        ) from exc
    except (
        URLError,
        TimeoutError,
        OSError,
    ) as exc:
        raise RevenueCatPromoProviderError(
            "RevenueCat promotional grant request failed."
        ) from exc

    if not raw:
        return {}

    try:
        payload = json.loads(
            raw.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise RevenueCatPromoProviderError(
            "RevenueCat returned invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise RevenueCatPromoProviderError(
            "RevenueCat returned an invalid response object."
        )

    return payload


def _resolve_entitlement_resource_id(
    *,
    entitlement_lookup_key: str,
) -> str:
    api_key, project_id = _credentials()

    encoded_project = quote(
        project_id,
        safe="",
    )

    next_url: str | None = (
        f"{REVENUECAT_V2_BASE_URL}"
        f"/projects/{encoded_project}"
        "/entitlements?limit=100"
    )

    page = 0

    while next_url is not None:
        page += 1

        if page > MAX_ENTITLEMENT_PAGES:
            raise RevenueCatPromoProviderError(
                "RevenueCat entitlement pagination exceeded the safety limit."
            )

        payload = _request_json(
            url=next_url,
            method="GET",
            api_key=api_key,
        )

        items = payload.get("items")

        if not isinstance(items, list):
            raise RevenueCatPromoProviderError(
                "RevenueCat entitlement list is missing items."
            )

        for item in items:
            if not isinstance(item, dict):
                continue

            if (
                item.get("lookup_key")
                != entitlement_lookup_key
            ):
                continue

            resource_id = item.get("id")

            if (
                isinstance(resource_id, str)
                and resource_id.strip()
            ):
                return resource_id.strip()

        raw_next = payload.get("next_page")

        if raw_next is None:
            next_url = None
            continue

        if (
            not isinstance(raw_next, str)
            or not raw_next.strip()
        ):
            raise RevenueCatPromoProviderError(
                "RevenueCat returned an invalid entitlement pagination URL."
            )

        candidate = urljoin(
            "https://api.revenuecat.com",
            raw_next.strip(),
        )

        _validate_url(candidate)

        parsed = urlparse(candidate)

        expected_prefix = (
            f"/v2/projects/{encoded_project}"
            "/entitlements"
        )

        if not parsed.path.startswith(
            expected_prefix
        ):
            raise RevenueCatPromoProviderError(
                "RevenueCat returned an unexpected entitlement pagination path."
            )

        next_url = candidate

    raise RevenueCatPromoConfigurationError(
        "RevenueCat entitlement lookup key could not be resolved."
    )


def grant_revenuecat_promotional_entitlement(
    *,
    user_id: UUID,
    entitlement_lookup_key: str,
    expires_at: datetime,
) -> dict[str, Any]:
    """
    Grant a RevenueCat promotional entitlement to one authenticated
    InternMatch App User ID.

    The secret API key never leaves the backend.
    """

    api_key, project_id = _credentials()

    entitlement_resource_id = (
        _resolve_entitlement_resource_id(
            entitlement_lookup_key=(
                entitlement_lookup_key
            ),
        )
    )

    encoded_project = quote(
        project_id,
        safe="",
    )

    encoded_customer = quote(
        str(user_id),
        safe="",
    )

    url = (
        f"{REVENUECAT_V2_BASE_URL}"
        f"/projects/{encoded_project}"
        f"/customers/{encoded_customer}"
        "/actions/grant_entitlement"
    )

    expires_at_ms = int(
        expires_at.timestamp() * 1000
    )

    return _request_json(
        url=url,
        method="POST",
        api_key=api_key,
        body={
            "entitlement_id":
                entitlement_resource_id,
            "expires_at":
                expires_at_ms,
        },
    )
