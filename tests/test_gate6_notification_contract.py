
"""Static architecture guards for Gate 6 notifications."""

from pathlib import Path


def test_notification_router_and_event_hooks_exist():
    router = Path(
        "backend/app/api/v1/router.py"
    ).read_text(
        encoding="utf-8"
    )

    application = Path(
        "backend/app/repositories/application.py"
    ).read_text(
        encoding="utf-8"
    )

    admin = Path(
        "backend/app/api/v1/endpoints/admin_internships.py"
    ).read_text(
        encoding="utf-8"
    )

    assert 'prefix="/notifications"' in router

    assert (
        "NotificationRepository.emit_application_status("
        in application
    )

    assert (
        'event_type="listing_published"'
        in admin
    )

    assert (
        'event_type="listing_changes_requested"'
        in admin
    )


def test_notification_api_is_identity_scoped():
    source = Path(
        "backend/app/api/v1/endpoints/notifications.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "current_user.user_id" in source
    assert "recipient_user_id" not in (
        source[
            source.index(
                "class"
            )
            if "class" in source
            else 0:
        ]
    ) or "payload.recipient_user_id" not in source

    assert "payload.recipient_user_id" not in source


def test_gate6c_native_client_and_server_delivery_exist():
    package = Path(
        "apps/mobile/package.json"
    ).read_text(
        encoding="utf-8"
    )

    notification_context = Path(
        "apps/mobile/src/context/NotificationContext.js"
    ).read_text(
        encoding="utf-8"
    )

    enqueue = Path(
        "backend/app/services/notification_enqueue.py"
    ).read_text(
        encoding="utf-8"
    )

    delivery = Path(
        "backend/app/services/notification_delivery.py"
    ).read_text(
        encoding="utf-8"
    )

    worker_task = Path(
        "worker/tasks/notification_delivery.py"
    ).read_text(
        encoding="utf-8"
    )

    # Gate 6B native client remains present.
    assert '"expo-notifications"' in package
    assert "getExpoPushTokenAsync" in notification_context
    assert "registerPushDevice" in notification_context

    # Gate 6C intentionally adds committed backend -> RQ -> Expo delivery.
    assert "enqueue_notification_delivery" in enqueue
    assert "queue.enqueue(" in enqueue
    assert "tasks.notification_delivery" in enqueue
    assert "exp.host/--/api/v2/push/send" in delivery
    assert "DeviceNotRegistered" in delivery
    assert "deliver_notification(" in worker_task





def test_gate6c_server_push_delivery_uses_post_commit_rq():
    repository = Path(
        "backend/app/repositories/notification.py"
    ).read_text(
        encoding="utf-8"
    )

    enqueue = Path(
        "backend/app/services/notification_enqueue.py"
    ).read_text(
        encoding="utf-8"
    )

    delivery = Path(
        "backend/app/services/notification_delivery.py"
    ).read_text(
        encoding="utf-8"
    )

    worker = Path(
        "worker/tasks/notification_delivery.py"
    ).read_text(
        encoding="utf-8"
    )

    assert '"after_commit"' in repository
    assert "PENDING_PUSH_IDS_KEY" in repository
    assert "queue.enqueue(" in enqueue
    assert "tasks.notification_delivery" in enqueue
    assert "exp.host/--/api/v2/push/send" in delivery
    assert "DeviceNotRegistered" in delivery
    assert "deliver_notification(" in worker



def test_gate6d_trust_events_notify_authoritative_employer_owner():
    organization = Path(
        "backend/app/api/v1/endpoints/employer_organizations.py"
    ).read_text(
        encoding="utf-8"
    )

    compliance = Path(
        "backend/app/api/v1/endpoints/employer_compliance.py"
    ).read_text(
        encoding="utf-8"
    )

    repository = Path(
        "backend/app/repositories/notification.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        'event_type="organization_verified"'
        in organization
    )

    assert (
        'event_type="organization_rejected"'
        in organization
    )

    assert (
        "recipient_user_id=organization.owner_user_id"
        in organization
    )

    assert (
        'event_type="compliance_approved"'
        in compliance
    )

    assert (
        'event_type="compliance_rejected"'
        in compliance
    )

    assert (
        "create_for_organization_owner("
        in compliance
    )

    assert (
        "organization.owner_user_id"
        in repository
    )


def test_gate6d_notifications_do_not_include_private_review_material():
    organization = Path(
        "backend/app/api/v1/endpoints/employer_organizations.py"
    ).read_text(
        encoding="utf-8"
    )

    compliance = Path(
        "backend/app/api/v1/endpoints/employer_compliance.py"
    ).read_text(
        encoding="utf-8"
    )

    markers = (
        (
            organization,
            'event_type="organization_verified"',
        ),
        (
            organization,
            'event_type="organization_rejected"',
        ),
        (
            compliance,
            'event_type="compliance_approved"',
        ),
        (
            compliance,
            'event_type="compliance_rejected"',
        ),
    )

    for source, marker in markers:
        start = source.index(
            marker
        )

        end = source.index(
            "db.commit()",
            start,
        )

        notification_block = source[
            start:end
        ]

        assert (
            "internal_note"
            not in notification_block
        )

        assert (
            "reason_code"
            not in notification_block
        )

        assert (
            "evidence"
            not in notification_block
        )
