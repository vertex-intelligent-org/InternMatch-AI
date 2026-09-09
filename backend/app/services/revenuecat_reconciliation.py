"""RevenueCat REST API v2 subscription reconciliation.

RevenueCat webhooks are the normal fast path. Reconciliation is a
server-side recovery path for delayed, missed, or out-of-order events.
"""

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SubscriptionEntitlement
from app.repositories.subscription import SubscriptionRepository
from app.services.subscription import (
    PRO_EMPLOYER_ENTITLEMENT_ID,
    PRO_STUDENT_ENTITLEMENT_ID,
    get_employer_subscription_snapshot,
    get_student_subscription_snapshot,
)

REVENUECAT_V2_BASE_URL = "https://api.revenuecat.com/v2"
RECONCILIATION_MIN_INTERVAL_SECONDS = 30
MAX_REVENUECAT_PAGES = 20


class RevenueCatReconciliationConfigurationError(RuntimeError):
    """RevenueCat server-side reconciliation is not configured correctly."""


class RevenueCatReconciliationProviderError(RuntimeError):
    """RevenueCat could not provide a usable subscription response."""


def _milliseconds_to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return None

    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)


def _normalize_upper(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    return value.strip().upper()


def _request_json(*, url: str, api_key: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=8) as response:
            raw_body = response.read()
    except HTTPError as exc:
        if exc.code == 401:
            raise RevenueCatReconciliationConfigurationError(
                "RevenueCat rejected the configured V2 secret API key."
            ) from exc

        if exc.code == 403:
            raise RevenueCatReconciliationConfigurationError(
                "RevenueCat V2 secret API key lacks required "
                "Customer Information read permission."
            ) from exc

        if exc.code == 404:
            raise RevenueCatReconciliationConfigurationError(
                "RevenueCat project or customer could not be resolved."
            ) from exc

        raise RevenueCatReconciliationProviderError(
            f"RevenueCat returned HTTP {exc.code}."
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RevenueCatReconciliationProviderError(
            "RevenueCat reconciliation request failed."
        ) from exc

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RevenueCatReconciliationProviderError(
            "RevenueCat returned invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise RevenueCatReconciliationProviderError(
            "RevenueCat returned an invalid response object."
        )

    return payload


def _validated_next_page(
    *,
    next_page: Any,
    project_id: str,
    user_id: UUID,
    resource_name: str,
) -> str | None:
    if next_page is None:
        return None

    if resource_name not in {"subscriptions", "active_entitlements"}:
        raise RevenueCatReconciliationProviderError(
            "Unexpected RevenueCat pagination resource."
        )

    if not isinstance(next_page, str) or not next_page.strip():
        raise RevenueCatReconciliationProviderError(
            "RevenueCat returned an invalid pagination URL."
        )

    candidate = urljoin("https://api.revenuecat.com", next_page.strip())
    parsed = urlparse(candidate)

    if parsed.scheme != "https" or parsed.netloc != "api.revenuecat.com":
        raise RevenueCatReconciliationProviderError(
            "RevenueCat returned an unexpected pagination host."
        )

    expected_path = (
        f"/v2/projects/{quote(project_id, safe='')}"
        f"/customers/{quote(str(user_id), safe='')}/{resource_name}"
    )

    if parsed.path != expected_path:
        raise RevenueCatReconciliationProviderError(
            "RevenueCat returned an unexpected pagination path."
        )

    return candidate


def _fetch_list_resource(
    *,
    user_id: UUID,
    project_id: str,
    api_key: str,
    resource_name: str,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    encoded_project_id = quote(project_id, safe="")
    encoded_user_id = quote(str(user_id), safe="")

    next_url: str | None = (
        f"{REVENUECAT_V2_BASE_URL}"
        f"/projects/{encoded_project_id}"
        f"/customers/{encoded_user_id}/{resource_name}"
    )

    if environment is not None:
        if resource_name != "subscriptions":
            raise RevenueCatReconciliationProviderError(
                "RevenueCat environment filtering is only supported "
                "for subscription reconciliation."
            )

        next_url += "?" + urlencode(
            {"environment": environment}
        )

    items_found: list[dict[str, Any]] = []
    page_count = 0

    while next_url is not None:
        page_count += 1

        if page_count > MAX_REVENUECAT_PAGES:
            raise RevenueCatReconciliationProviderError(
                "RevenueCat pagination exceeded the safety limit."
            )

        payload = _request_json(
            url=next_url,
            api_key=api_key,
        )

        items = payload.get("items")
        if not isinstance(items, list):
            raise RevenueCatReconciliationProviderError(
                "RevenueCat list response is missing items."
            )

        for item in items:
            if isinstance(item, dict):
                items_found.append(item)

        next_url = _validated_next_page(
            next_page=payload.get("next_page"),
            project_id=project_id,
            user_id=user_id,
            resource_name=resource_name,
        )

    return items_found


def _fetch_revenuecat_subscriptions(
    *,
    user_id: UUID,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    int,
]:
    """Fetch RevenueCat v2 subscription and active-entitlement state."""

    api_key = (settings.REVENUECAT_SECRET_KEY or "").strip()
    project_id = (settings.REVENUECAT_PROJECT_ID or "").strip()
    environment = (
        settings.REVENUECAT_ENVIRONMENT or ""
    ).strip().lower()

    if not api_key:
        raise RevenueCatReconciliationConfigurationError(
            "RevenueCat V2 secret API key is not configured."
        )

    if not project_id:
        raise RevenueCatReconciliationConfigurationError(
            "RevenueCat project ID is not configured."
        )

    if environment not in {"sandbox", "production"}:
        raise RevenueCatReconciliationConfigurationError(
            "RevenueCat environment must be sandbox or production."
        )

    subscriptions = _fetch_list_resource(
        user_id=user_id,
        project_id=project_id,
        api_key=api_key,
        resource_name="subscriptions",
        environment=environment,
    )

    # RevenueCat's active-entitlements resource has no environment
    # filter. We only need it to guard against the Test Store stale
    # gives_access state observed after accelerated sandbox expiry.
    has_test_store_subscription = any(
        _normalize_upper(subscription.get("store"))
        == "TEST_STORE"
        for subscription in subscriptions
    )

    if has_test_store_subscription:
        active_entitlements = _fetch_list_resource(
            user_id=user_id,
            project_id=project_id,
            api_key=api_key,
            resource_name="active_entitlements",
        )
    else:
        active_entitlements = []

    # Timestamp only after both provider snapshots were fetched.
    # A delayed webhook older than this reconciliation snapshot
    # must not resurrect stale entitlement state.
    snapshot_timestamp_ms = int(
        datetime.now(timezone.utc).timestamp() * 1000
    )

    return (
        subscriptions,
        active_entitlements,
        snapshot_timestamp_ms,
    )

def _entitlement_items(subscription: dict[str, Any]) -> list[dict[str, Any]]:
    container = subscription.get("entitlements")
    if not isinstance(container, dict):
        return []

    items = container.get("items")
    if not isinstance(items, list):
        return []

    return [item for item in items if isinstance(item, dict)]


def _contains_entitlement(
    subscription: dict[str, Any],
    *,
    entitlement_id: str,
) -> bool:
    return any(
        item.get("lookup_key") == entitlement_id
        for item in _entitlement_items(subscription)
    )


def _entitlement_ids(
    subscriptions: list[dict[str, Any]],
    *,
    entitlement_id: str,
) -> set[str]:
    ids: set[str] = set()

    for subscription in subscriptions:
        for entitlement in _entitlement_items(subscription):
            if (
                entitlement.get("lookup_key")
                != entitlement_id
            ):
                continue

            entitlement_id = entitlement.get("id")

            if isinstance(entitlement_id, str) and entitlement_id:
                ids.add(entitlement_id)

    return ids


def _matching_active_entitlement(
    *,
    subscriptions: list[dict[str, Any]],
    active_entitlements: list[dict[str, Any]],
    entitlement_id: str,
) -> dict[str, Any] | None:
    pro_entitlement_ids = _entitlement_ids(
        subscriptions,
        entitlement_id=entitlement_id,
    )

    for active_entitlement in active_entitlements:
        entitlement_id = active_entitlement.get("entitlement_id")

        if entitlement_id in pro_entitlement_ids:
            return active_entitlement

    return None


def _subscription_sort_timestamp(subscription: dict[str, Any]) -> int:
    values: list[int] = []

    for field in (
        "ends_at",
        "current_period_ends_at",
        "current_period_starts_at",
        "starts_at",
    ):
        try:
            value = int(subscription.get(field))
        except (TypeError, ValueError):
            continue

        values.append(value)

    return max(values, default=0)


def _select_relevant_subscription(
    subscriptions: list[dict[str, Any]],
    *,
    entitlement_id: str,
) -> dict[str, Any] | None:
    relevant = [
        subscription
        for subscription in subscriptions
        if _contains_entitlement(subscription, entitlement_id=entitlement_id)
    ]

    if not relevant:
        return None

    access_granting = [
        subscription
        for subscription in relevant
        if subscription.get("gives_access") is True
    ]

    candidates = access_granting or relevant

    return max(
        candidates,
        key=_subscription_sort_timestamp,
    )


def _extract_store_product_identifier(
    subscription: dict[str, Any],
    *,
    entitlement_id: str,
) -> str | None:
    revenuecat_product_id = subscription.get("product_id")

    if not isinstance(revenuecat_product_id, str):
        return None

    for entitlement in _entitlement_items(subscription):
        if entitlement.get("lookup_key") != entitlement_id:
            continue

        products = entitlement.get("products")
        if not isinstance(products, dict):
            continue

        items = products.get("items")
        if not isinstance(items, list):
            continue

        for product in items:
            if not isinstance(product, dict):
                continue

            if product.get("id") != revenuecat_product_id:
                continue

            store_identifier = product.get("store_identifier")

            if isinstance(store_identifier, str) and store_identifier:
                return store_identifier

    return None


def _internal_status(
    subscription: dict[str, Any],
    *,
    gives_access: bool,
) -> str:
    provider_status = subscription.get("status")

    if not isinstance(provider_status, str):
        return "active" if gives_access else "inactive"

    provider_status = provider_status.strip().lower()

    if gives_access:
        if provider_status == "in_grace_period":
            return "billing_issue"

        return "active"

    if provider_status == "expired":
        return "expired"

    if provider_status == "paused":
        return "paused"

    if provider_status in {"in_billing_retry", "incomplete"}:
        return "billing_issue"

    return provider_status or "inactive"


def _will_renew(subscription: dict[str, Any]) -> bool:
    status = subscription.get("auto_renewal_status")

    return status in {
        "will_renew",
        "will_change_product",
        "has_already_renewed",
    }


def _reconcile_subscription(
    db: Session,
    *,
    user_id: UUID,
    entitlement_id: str,
    snapshot_getter,
    min_interval_seconds: int = RECONCILIATION_MIN_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Reconcile one supported Pro entitlement against RevenueCat REST API v2."""

    now = datetime.now(timezone.utc)

    entitlement = SubscriptionRepository.get_entitlement(
        db,
        user_id=user_id,
        entitlement_id=entitlement_id,
    )

    if (
        entitlement is not None
        and entitlement.updated_at is not None
        and min_interval_seconds > 0
    ):
        updated_at = entitlement.updated_at

        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        else:
            updated_at = updated_at.astimezone(timezone.utc)

        if (now - updated_at).total_seconds() < min_interval_seconds:
            return {
                "outcome": "skipped_recent",
                "subscription": snapshot_getter(
                    db,
                    user_id=user_id,
                ),
            }

    (
        subscriptions,
        active_entitlements,
        snapshot_timestamp_ms,
    ) = _fetch_revenuecat_subscriptions(
        user_id=user_id,
    )

    selected = _select_relevant_subscription(
        subscriptions,
        entitlement_id=entitlement_id,
    )

    active_entitlement = _matching_active_entitlement(
        subscriptions=subscriptions,
        active_entitlements=active_entitlements,
        entitlement_id=entitlement_id,
    )

    if entitlement is None:
        entitlement = SubscriptionEntitlement(
            user_id=user_id,
            entitlement_id=entitlement_id,
            status="free",
            is_active=False,
            will_renew=False,
        )
        db.add(entitlement)

    if selected is None:
        entitlement.status = "free"
        entitlement.is_active = False
        entitlement.will_renew = False
        entitlement.current_period_started_at = None
        entitlement.expires_at = None
    else:
        provider_gives_access = selected.get("gives_access") is True

        period_started_at = _milliseconds_to_datetime(
            selected.get("current_period_starts_at")
        )

        if period_started_at is not None:
            entitlement.current_period_started_at = period_started_at

        access_end = _milliseconds_to_datetime(
            selected.get("ends_at")
        )
        if access_end is None:
            access_end = _milliseconds_to_datetime(
                selected.get("current_period_ends_at")
            )

        provider_store = _normalize_upper(selected.get("store"))
        gives_access = provider_gives_access

        if (
            provider_gives_access
            and provider_store == "TEST_STORE"
            and access_end is not None
            and access_end <= now
            and active_entitlement is None
        ):
            gives_access = False

        entitlement.status = _internal_status(
            selected,
            gives_access=gives_access,
        )

        if (
            not gives_access
            and access_end is not None
            and access_end <= now
        ):
            entitlement.status = "expired"

        entitlement.is_active = gives_access
        entitlement.will_renew = (
            _will_renew(selected) if gives_access else False
        )

        if active_entitlement is not None:
            entitlement.expires_at = _milliseconds_to_datetime(
                active_entitlement.get("expires_at")
            )
        else:
            entitlement.expires_at = access_end

        store_product_identifier = _extract_store_product_identifier(
            selected,
            entitlement_id=entitlement_id,
        )

        if store_product_identifier is not None:
            entitlement.product_id = store_product_identifier

        environment = _normalize_upper(selected.get("environment"))
        if environment is not None:
            entitlement.environment = environment

        if provider_store is not None:
            entitlement.store = provider_store

        if entitlement.status == "active":
            entitlement.cancellation_reason = None
            entitlement.expiration_reason = None

    current_barrier = entitlement.last_event_timestamp_ms or 0
    entitlement.last_event_timestamp_ms = max(
        current_barrier,
        snapshot_timestamp_ms,
    )
    entitlement.last_event_id = f"reconcile:v2:{snapshot_timestamp_ms}"
    entitlement.last_event_type = "RECONCILIATION"

    db.commit()
    db.refresh(entitlement)

    return {
        "outcome": "reconciled",
        "subscription": snapshot_getter(
            db,
            user_id=user_id,
        ),
    }


def reconcile_student_subscription(
    db: Session,
    *,
    user_id: UUID,
    min_interval_seconds: int = RECONCILIATION_MIN_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Reconcile Student Pro state against RevenueCat REST API v2."""

    return _reconcile_subscription(
        db,
        user_id=user_id,
        entitlement_id=PRO_STUDENT_ENTITLEMENT_ID,
        snapshot_getter=get_student_subscription_snapshot,
        min_interval_seconds=min_interval_seconds,
    )


def reconcile_employer_subscription(
    db: Session,
    *,
    user_id: UUID,
    min_interval_seconds: int = RECONCILIATION_MIN_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Reconcile Employer Pro state against RevenueCat REST API v2."""

    return _reconcile_subscription(
        db,
        user_id=user_id,
        entitlement_id=PRO_EMPLOYER_ENTITLEMENT_ID,
        snapshot_getter=get_employer_subscription_snapshot,
        min_interval_seconds=min_interval_seconds,
    )
