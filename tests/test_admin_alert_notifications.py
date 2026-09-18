"""Automated admin operational-alert contracts."""

from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.db.models import (
    Application,
    InternshipListing,
    StudentProfile,
    UserNotification,
)
from app.repositories.application import (
    ApplicationRepository,
)
from app.repositories.notification import (
    NotificationRepository,
)
from app.services.notification_email_delivery import (
    ADMIN_ALERT_EVENT_TYPES,
    deliver_admin_alert_email,
)

from tests.db import TestingSessionLocal


class _FakeSMTP:
    sent_messages = []

    def __init__(
        self,
        host,
        port,
        timeout,
        **kwargs,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False

    def ehlo(self):
        return None

    def starttls(
        self,
        context,
    ):
        return None

    def login(
        self,
        username,
        password,
    ):
        return None

    def send_message(
        self,
        message,
        *,
        from_addr,
        to_addrs,
    ):
        self.sent_messages.append(
            {
                "message": message,
                "from_addr": from_addr,
                "to_addrs": list(
                    to_addrs
                ),
            }
        )


def test_admin_factory_creates_one_notification_per_admin_and_one_email_job(
    monkeypatch,
):
    admin_a = uuid4()
    admin_b = uuid4()

    original_admin_ids = (
        settings.ADMIN_USER_IDS
    )

    settings.ADMIN_USER_IDS = (
        f"{admin_b},{admin_a}"
    )

    queued_email = []

    monkeypatch.setattr(
        (
            "app.services.notification_enqueue."
            "enqueue_admin_alert_email_delivery"
        ),
        lambda notification_id:
            queued_email.append(
                str(notification_id)
            ),
    )

    db = TestingSessionLocal()

    try:
        rows = (
            NotificationRepository
            .create_for_admins(
                db,
                event_type=(
                    "organization_review_requested"
                ),
                entity_type=(
                    "employer_organization"
                ),
                entity_id=uuid4(),
                data={
                    "display_name":
                        "Example Company"
                },
                dedupe_key=(
                    "admin-alert:test:"
                    "organization"
                ),
            )
        )

        assert len(rows) == 2
        assert queued_email == []

        db.commit()

        assert len(queued_email) == 1

        persisted = (
            db.query(UserNotification)
            .filter(
                UserNotification.event_type
                == "organization_review_requested"
            )
            .all()
        )

        assert len(persisted) == 2
    finally:
        settings.ADMIN_USER_IDS = (
            original_admin_ids
        )
        db.close()


def test_admin_curated_application_routes_to_admin_notifications():
    admin_user_id = uuid4()
    candidate_user_id = uuid4()

    original_admin_ids = (
        settings.ADMIN_USER_IDS
    )

    settings.ADMIN_USER_IDS = str(
        admin_user_id
    )

    db = TestingSessionLocal()

    try:
        profile = StudentProfile(
            user_id=candidate_user_id,
            full_name="Candidate Example",
            preferences={
                "account_type": "intern",
            },
        )

        db.add(profile)
        db.flush()

        listing = InternshipListing(
            employer_user_id=None,
            employer_organization_id=None,
            listing_source="curated",
            publication_status="published",
            is_active=True,
            title="Admin Opportunity",
            company="InternMatch AI Team",
            location="Remote",
            work_type="remote",
            description="Admin-curated test.",
            required_skills=[],
            preferred_skills=[],
            metadata_json={
                "created_via":
                    "admin_console",
                "created_by_admin_user_id":
                    str(admin_user_id),
            },
        )

        db.add(listing)
        db.flush()

        application = Application(
            student_id=profile.id,
            internship_id=listing.id,
            status="saved",
            generated_cover_letter="Test",
        )

        db.add(application)
        db.flush()

        ApplicationRepository.update_status(
            db=db,
            application=application,
            status="applied",
        )

        db.commit()

        notification = db.query(
            UserNotification
        ).filter(
            UserNotification.recipient_user_id
            == admin_user_id,
            UserNotification.event_type
            == (
                "admin_curated_"
                "application_submitted"
            ),
        ).one()

        assert (
            "Candidate Example"
            in notification.data_json
        )

        assert (
            "Admin Opportunity"
            in notification.data_json
        )
    finally:
        settings.ADMIN_USER_IDS = (
            original_admin_ids
        )
        db.close()


def test_admin_email_delivery_uses_fixed_template_and_no_ai(
    monkeypatch,
):
    original_values = {
        "ADMIN_ALERT_EMAILS":
            settings.ADMIN_ALERT_EMAILS,
        "SMTP_HOST":
            settings.SMTP_HOST,
        "SMTP_PORT":
            settings.SMTP_PORT,
        "SMTP_USERNAME":
            settings.SMTP_USERNAME,
        "SMTP_PASSWORD":
            settings.SMTP_PASSWORD,
        "SMTP_FROM_EMAIL":
            settings.SMTP_FROM_EMAIL,
        "SMTP_SECURITY":
            settings.SMTP_SECURITY,
    }

    settings.ADMIN_ALERT_EMAILS = (
        "admin@example.com"
    )
    settings.SMTP_HOST = "smtp.example.com"
    settings.SMTP_PORT = 587
    settings.SMTP_USERNAME = ""
    settings.SMTP_PASSWORD = ""
    settings.SMTP_FROM_EMAIL = (
        "alerts@example.com"
    )
    settings.SMTP_SECURITY = "starttls"

    _FakeSMTP.sent_messages = []

    monkeypatch.setattr(
        (
            "app.services."
            "notification_email_delivery."
            "smtplib.SMTP"
        ),
        _FakeSMTP,
    )

    db = TestingSessionLocal()

    try:
        notification = UserNotification(
            recipient_user_id=uuid4(),
            event_type=(
                "listing_review_requested"
            ),
            entity_type="internship",
            entity_id=uuid4(),
            data_json=(
                '{"title":"Backend Intern",'
                '"company":"Example Company"}'
            ),
        )

        db.add(notification)
        db.commit()

        result = (
            deliver_admin_alert_email(
                db,
                notification_id=(
                    notification.id
                ),
            )
        )

        assert result.attempted == 1
        assert result.sent == 1
        assert len(
            _FakeSMTP.sent_messages
        ) == 1

        subject = str(
            _FakeSMTP
            .sent_messages[0]["message"][
                "Subject"
            ]
        )

        assert (
            "Opportunity review"
            in subject
        )
    finally:
        for key, value in (
            original_values.items()
        ):
            setattr(
                settings,
                key,
                value,
            )

        db.close()


def test_admin_alerts_are_deterministic_and_ai_free():
    assert ADMIN_ALERT_EVENT_TYPES == {
        "admin_curated_application_submitted",
        "organization_review_requested",
        "listing_review_requested",
        "compliance_review_requested",
    }

    service = (
        Path(__file__).resolve()
        .parents[1]
        / "backend/app/services/"
        "notification_email_delivery.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    assert "openai" not in service
    assert "gemini" not in service
    assert "generate_" not in service


def test_review_submission_hooks_are_present():
    root = (
        Path(__file__).resolve()
        .parents[1]
    )

    sources = {
        "organization":
            "backend/app/api/v1/endpoints/"
            "employer_organizations.py",

        "listing":
            "backend/app/api/v1/endpoints/"
            "internships.py",

        "compliance":
            "backend/app/api/v1/endpoints/"
            "employer_compliance.py",
    }

    expected = {
        "organization":
            "organization_review_requested",

        "listing":
            "listing_review_requested",

        "compliance":
            "compliance_review_requested",
    }

    for key, relative_path in (
        sources.items()
    ):
        text = (
            root / relative_path
        ).read_text(
            encoding="utf-8"
        )

        assert expected[key] in text
