"""Deterministic SMTP delivery for administrative operational alerts."""

from __future__ import annotations

import json
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import UserNotification

ADMIN_ALERT_EVENT_TYPES = frozenset(
    {
        "admin_curated_application_submitted",
        "organization_review_requested",
        "listing_review_requested",
        "compliance_review_requested",
    }
)


@dataclass(frozen=True)
class AdminEmailDeliveryResult:
    attempted: int
    sent: int


def _data(
    notification: UserNotification,
) -> dict:
    try:
        parsed = json.loads(
            notification.data_json
            or "{}"
        )
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return {}

    return (
        parsed
        if isinstance(parsed, dict)
        else {}
    )


def _recipients() -> list[str]:
    values: list[str] = []

    for raw_value in (
        settings.ADMIN_ALERT_EMAILS
        or ""
    ).split(","):
        candidate = raw_value.strip()

        if (
            not candidate
            or "@" not in candidate
        ):
            continue

        if candidate not in values:
            values.append(candidate)

    return values


def _admin_url(
    path: str,
) -> str:
    base = (
        settings.ADMIN_BASE_URL
        or "https://admin.internmatch.college"
    ).strip().rstrip("/")

    suffix = (
        path
        if path.startswith("/")
        else f"/{path}"
    )

    return base + suffix


def _render(
    notification: UserNotification,
) -> tuple[str, str]:
    data = _data(notification)
    event_type = notification.event_type

    if (
        event_type
        == "admin_curated_application_submitted"
    ):
        title = str(
            data.get(
                "listing_title",
                "Admin opportunity",
            )
        )

        candidate_name = str(
            data.get(
                "candidate_name",
                "Candidate",
            )
        )

        internship_id = str(
            data.get(
                "internship_id",
                "",
            )
        )

        application_id = str(
            data.get(
                "application_id",
                "",
            )
        )

        subject = (
            "[InternMatch Admin] "
            f"New application ? {title}"
        )

        body = "\n".join(
            [
                "A candidate submitted an application "
                "to an InternMatch-admin opportunity.",
                "",
                f"Candidate: {candidate_name}",
                f"Opportunity: {title}",
                f"Application ID: {application_id}",
                "",
                "Review applicants:",
                _admin_url(
                    f"/listings/{internship_id}/applicants"
                ),
            ]
        )

        return subject, body

    if (
        event_type
        == "organization_review_requested"
    ):
        display_name = str(
            data.get(
                "display_name",
                "Employer organization",
            )
        )

        subject = (
            "[InternMatch Admin] "
            f"Organization review ? {display_name}"
        )

        body = "\n".join(
            [
                "An employer organization is waiting "
                "for administrative verification.",
                "",
                f"Organization: {display_name}",
                (
                    "Legal name: "
                    + str(
                        data.get(
                            "legal_name",
                            "",
                        )
                    )
                ),
                (
                    "Business email: "
                    + str(
                        data.get(
                            "business_email",
                            "",
                        )
                    )
                ),
                (
                    "Representative: "
                    + str(
                        data.get(
                            "representative_name",
                            "",
                        )
                    )
                ),
                "",
                "Open organization review:",
                _admin_url("/"),
            ]
        )

        return subject, body

    if (
        event_type
        == "listing_review_requested"
    ):
        title = str(
            data.get(
                "title",
                "Employer opportunity",
            )
        )

        company = str(
            data.get(
                "company",
                "Employer",
            )
        )

        subject = (
            "[InternMatch Admin] "
            f"Opportunity review ? {title}"
        )

        body = "\n".join(
            [
                "An employer opportunity is waiting "
                "for human review.",
                "",
                f"Company: {company}",
                f"Opportunity: {title}",
                "",
                "Open listing review:",
                _admin_url("/listings"),
            ]
        )

        return subject, body

    if (
        event_type
        == "compliance_review_requested"
    ):
        company = str(
            data.get(
                "company",
                "Employer organization",
            )
        )

        subject = (
            "[InternMatch Admin] "
            f"Compliance review ? {company}"
        )

        body = "\n".join(
            [
                "New employer compliance evidence "
                "is waiting for administrative review.",
                "",
                f"Organization: {company}",
                (
                    "Claim type: "
                    + str(
                        data.get(
                            "claim_type",
                            "",
                        )
                    )
                ),
                (
                    "Jurisdiction: "
                    + str(
                        data.get(
                            "jurisdiction_country_code",
                            "",
                        )
                    )
                ),
                "",
                "Open compliance review:",
                _admin_url("/compliance"),
                "",
                "Security note: evidence documents are "
                "not attached to this email. Review them "
                "only inside the authenticated admin console.",
            ]
        )

        return subject, body

    raise ValueError(
        "Unsupported administrative alert event."
    )


def deliver_admin_alert_email(
    db: Session,
    *,
    notification_id: UUID,
) -> AdminEmailDeliveryResult:
    notification = db.get(
        UserNotification,
        notification_id,
    )

    if (
        notification is None
        or notification.event_type
        not in ADMIN_ALERT_EVENT_TYPES
    ):
        return AdminEmailDeliveryResult(
            attempted=0,
            sent=0,
        )

    recipients = _recipients()

    if not recipients:
        return AdminEmailDeliveryResult(
            attempted=0,
            sent=0,
        )

    host = (
        settings.SMTP_HOST
        or ""
    ).strip()

    from_email = (
        settings.SMTP_FROM_EMAIL
        or ""
    ).strip()

    username = (
        settings.SMTP_USERNAME
        or ""
    ).strip()

    password = (
        settings.SMTP_PASSWORD
        or ""
    ).strip()

    security = (
        settings.SMTP_SECURITY
        or "starttls"
    ).strip().lower()

    if (
        not host
        or not from_email
    ):
        raise RuntimeError(
            "SMTP configuration is incomplete."
        )

    if bool(username) != bool(password):
        raise RuntimeError(
            "SMTP authentication configuration "
            "is incomplete."
        )

    if security not in {
        "starttls",
        "ssl",
        "none",
    }:
        raise RuntimeError(
            "SMTP security mode is invalid."
        )

    subject, body = _render(
        notification
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(
        (
            (
                settings.SMTP_FROM_NAME
                or "InternMatch AI"
            ).strip(),
            from_email,
        )
    )
    message["To"] = ", ".join(
        recipients
    )
    message.set_content(body)

    context = ssl.create_default_context()

    if security == "ssl":
        smtp_client = smtplib.SMTP_SSL(
            host,
            settings.SMTP_PORT,
            timeout=10,
            context=context,
        )
    else:
        smtp_client = smtplib.SMTP(
            host,
            settings.SMTP_PORT,
            timeout=10,
        )

    with smtp_client as smtp:
        if security == "starttls":
            smtp.ehlo()
            smtp.starttls(
                context=context
            )
            smtp.ehlo()

        if username:
            smtp.login(
                username,
                password,
            )

        smtp.send_message(
            message,
            from_addr=from_email,
            to_addrs=recipients,
        )

    return AdminEmailDeliveryResult(
        attempted=len(recipients),
        sent=len(recipients),
    )
