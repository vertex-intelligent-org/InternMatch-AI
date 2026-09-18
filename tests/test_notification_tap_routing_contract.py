"""Mobile notification tap-routing contracts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (
        ROOT
        .joinpath(path)
        .read_text(
            encoding="utf-8"
        )
    )


def test_push_payload_contains_only_safe_routing_metadata():
    source = _read(
        "backend/app/services/"
        "notification_delivery.py"
    )

    for key in (
        "application_id",
        "internship_id",
        "organization_id",
        "claim_id",
        "status",
    ):
        assert f'"{key}"' in source

    assert "internal_note" not in source
    assert "evidence_document" not in source


def test_notification_route_resolver_covers_product_events():
    source = _read(
        "apps/mobile/src/services/"
        "notificationRouting.js"
    )

    expected = (
        "application_status_changed",
        "application_submitted",
        "listing_changes_requested",
        "listing_published",
        "organization_verified",
        "organization_rejected",
        "compliance_approved",
        "compliance_rejected",
        "ApplicationDetail",
        "EmployerApplicantDetail",
        "CreateOpportunity",
        "EmployerVerification",
        "EmployerCompliance",
    )

    for marker in expected:
        assert marker in source


def test_inbox_uses_shared_notification_router():
    source = _read(
        "apps/mobile/src/screens/"
        "NotificationsScreen.js"
    )

    assert (
        "resolveNotificationDestination"
        in source
    )

    assert (
        "destination.name"
        in source
    )


def test_push_response_is_routed_by_root_navigation():
    context = _read(
        "apps/mobile/src/context/"
        "NotificationContext.js"
    )

    navigator = _read(
        "apps/mobile/src/navigation/"
        "RootNavigator.js"
    )

    assert (
        "setPendingNotificationResponse"
        in context
    )

    assert (
        "addNotificationResponseReceivedListener"
        in context
    )

    assert (
        "pendingNotificationResponse"
        in navigator
    )

    assert (
        "resolveNotificationDestination"
        in navigator
    )

    assert (
        "navigationRef.navigate("
        in navigator
    )

    assert (
        "profile?.user_id"
        in navigator
    )
