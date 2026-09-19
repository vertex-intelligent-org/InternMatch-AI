import json
import re
from uuid import uuid4

from app.db.models import (
    InternshipListing,
    StudentProfile,
    UserNotification,
)
from app.services import opportunity_alert_enqueue
from app.services.notification_delivery import _copy
from app.services.notification_user_email_delivery import (
    is_user_notification_email_event,
)
from app.services.opportunity_alerts import (
    create_new_opportunity_alerts,
)
from sqlalchemy import select

from tests.db import TestingSessionLocal


def _profile(
    db,
    *,
    enabled,
    account_type="intern",
):
    profile = StudentProfile(
        id=uuid4(),
        user_id=uuid4(),
        full_name="Candidate",
        preferences={
            "account_type": account_type,
            "new_opportunity_alerts_enabled": enabled,
        },
    )
    db.add(profile)
    return profile


def _listing(
    db,
    *,
    publication_status="published",
):
    listing = InternshipListing(
        id=uuid4(),
        employer_user_id=uuid4(),
        listing_source="employer",
        publication_status=publication_status,
        title="Software Engineering Intern",
        company="Acme",
        location="Istanbul",
        work_type="Hybrid",
        description="Build production software.",
        required_skills=["Python"],
        preferred_skills=["FastAPI"],
        is_active=(
            publication_status == "published"
        ),
    )
    db.add(listing)
    db.flush()
    return listing


def test_new_opportunity_alerts_require_explicit_candidate_opt_in():
    db = TestingSessionLocal()

    try:
        opted_in = _profile(
            db,
            enabled=True,
        )
        _profile(
            db,
            enabled=False,
        )
        _profile(
            db,
            enabled=True,
            account_type="employer",
        )

        listing = _listing(db)

        ensured = create_new_opportunity_alerts(
            db,
            internship_id=listing.id,
        )

        rows = list(
            db.scalars(
                select(UserNotification).where(
                    UserNotification.event_type
                    == "new_opportunity_published"
                )
            ).all()
        )

        assert ensured == 1
        assert len(rows) == 1
        assert (
            rows[0].recipient_user_id
            == opted_in.user_id
        )

        data = json.loads(
            rows[0].data_json
        )

        assert data["internship_id"] == str(
            listing.id
        )
        assert data["company"] == "Acme"
        assert (
            data["title"]
            == "Software Engineering Intern"
        )
    finally:
        db.rollback()
        db.close()


def test_new_opportunity_alert_is_idempotent_per_user_and_listing():
    db = TestingSessionLocal()

    try:
        _profile(
            db,
            enabled=True,
        )

        listing = _listing(db)

        create_new_opportunity_alerts(
            db,
            internship_id=listing.id,
        )
        create_new_opportunity_alerts(
            db,
            internship_id=listing.id,
        )

        rows = list(
            db.scalars(
                select(UserNotification).where(
                    UserNotification.event_type
                    == "new_opportunity_published"
                )
            ).all()
        )

        assert len(rows) == 1
    finally:
        db.rollback()
        db.close()


def test_unpublished_listing_never_fans_out():
    db = TestingSessionLocal()

    try:
        _profile(
            db,
            enabled=True,
        )

        listing = _listing(
            db,
            publication_status="under_review",
        )

        ensured = create_new_opportunity_alerts(
            db,
            internship_id=listing.id,
        )

        assert ensured == 0
        assert (
            db.scalar(
                select(UserNotification.id).where(
                    UserNotification.event_type
                    == "new_opportunity_published"
                )
            )
            is None
        )
    finally:
        db.rollback()
        db.close()


def test_new_opportunity_alert_never_triggers_transactional_email():
    assert (
        is_user_notification_email_event(
            event_type=(
                "new_opportunity_published"
            ),
            data={},
        )
        is False
    )


def test_new_opportunity_push_copy_is_localized():
    data = {
        "company": "Acme",
        "title": "Software Engineering Intern",
    }

    for locale in (
        "en",
        "tr",
        "ar",
    ):
        title, body = _copy(
            event_type=(
                "new_opportunity_published"
            ),
            locale=locale,
            data=data,
        )

        assert title
        assert "Acme" in body
        assert (
            "Software Engineering Intern"
            in body
        )

def test_opportunity_alert_preference_endpoint_preserves_other_preferences(
    client,
    mock_supabase_auth,
):
    _ = mock_supabase_auth

    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Preference Candidate",
            headline="Backend Student",
            preferences={
                "account_type": "intern",
                "work_types": ["Remote"],
                "target_roles": ["Backend"],
                "new_opportunity_alerts_enabled": False,
            },
        )

        db.add(profile)
        db.commit()
    finally:
        db.close()

    response = client.put(
        (
            "/api/v1/notifications/preferences/"
            "opportunity-alerts"
        ),
        headers={
            "Authorization":
                f"Bearer valid-user-{user_id}"
        },
        json={
            "enabled": True,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
    }

    db = TestingSessionLocal()

    try:
        stored = db.scalar(
            select(StudentProfile).where(
                StudentProfile.user_id
                == user_id
            )
        )

        assert stored is not None

        preferences = dict(
            stored.preferences or {}
        )

        assert (
            preferences[
                "new_opportunity_alerts_enabled"
            ]
            is True
        )

        assert preferences["account_type"] == "intern"
        assert preferences["work_types"] == ["Remote"]
        assert preferences["target_roles"] == ["Backend"]
        assert stored.full_name == "Preference Candidate"
        assert stored.headline == "Backend Student"
    finally:
        db.close()

    response = client.get(
        (
            "/api/v1/notifications/preferences/"
            "opportunity-alerts"
        ),
        headers={
            "Authorization":
                f"Bearer valid-user-{user_id}"
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
    }


def test_opportunity_alert_fanout_job_id_is_rq_safe(
    monkeypatch,
):
    captured = {}

    class FakeQueue:
        def __init__(
            self,
            *args,
            **kwargs,
        ):
            pass

        def enqueue(
            self,
            task_name,
            internship_id,
            **kwargs,
        ):
            captured["task_name"] = task_name
            captured["internship_id"] = internship_id
            captured["job_id"] = kwargs["job_id"]
            return object()

    monkeypatch.setattr(
        opportunity_alert_enqueue,
        "Queue",
        FakeQueue,
    )

    monkeypatch.setattr(
        opportunity_alert_enqueue.Redis,
        "from_url",
        lambda *args, **kwargs: object(),
    )

    internship_id = uuid4()

    opportunity_alert_enqueue.enqueue_new_opportunity_alert_fanout(
        internship_id
    )

    assert captured["task_name"] == (
        "tasks.opportunity_alert_fanout."
        "run_new_opportunity_alert_fanout"
    )

    assert captured["internship_id"] == str(
        internship_id
    )

    assert captured["job_id"].startswith(
        "opportunity-alert-fanout-"
    )

    assert re.fullmatch(
        r"[A-Za-z0-9_-]+",
        captured["job_id"],
    )


def test_new_opportunity_arabic_push_fallback_is_localized():
    title, body = _copy(
        event_type="new_opportunity_published",
        locale="ar",
        data={},
    )

    assert title
    assert (
        "\u0625\u062d\u062f\u0649 "
        "\u0627\u0644\u0634\u0631\u0643\u0627\u062a"
        in body
    )
    assert (
        "\u0645\u062a\u062f\u0631\u0628"
        in body
    )
    assert "A company" not in body
    assert "an intern" not in body
