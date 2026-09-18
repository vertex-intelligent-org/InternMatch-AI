"""Transactional SMTP delivery for user-facing notifications."""

from __future__ import annotations

import html
import json
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import PushDevice, UserNotification

USER_NOTIFICATION_EMAIL_EVENT_TYPES = frozenset(
    {
        "application_submitted",
        "application_status_changed",
        "listing_published",
        "listing_changes_requested",
        "organization_verified",
        "organization_rejected",
        "compliance_approved",
        "compliance_rejected",
    }
)

APPLICATION_EMAIL_STATUSES = frozenset(
    {
        "interviewing",
        "accepted",
        "rejected",
    }
)

PUBLIC_APP_URL = "https://internmatch.college"


COPY = {
    "en": {
        "application_submitted": (
            "New application received",
            "You received a new application",
            "A candidate applied to one of your opportunities.",
        ),
        "application_interviewing": (
            "You?ve moved to the interview stage",
            "Your application is moving forward",
            "The employer moved your application to the interview stage.",
        ),
        "application_accepted": (
            "Congratulations ? your application was accepted",
            "Congratulations!",
            "Your application has been accepted.",
        ),
        "application_rejected": (
            "Update on your application",
            "Your application has been reviewed",
            "The employer decided not to proceed with your application at this time.",
        ),
        "listing_published": (
            "Your opportunity is now live",
            "Your opportunity was published",
            "Your opportunity passed review and is now visible to candidates.",
        ),
        "listing_changes_requested": (
            "Changes are required for your opportunity",
            "Your opportunity needs changes",
            "Please review the requested changes before submitting the opportunity again.",
        ),
        "organization_verified": (
            "Your organization has been verified",
            "Organization verified",
            "Your employer organization verification was approved.",
        ),
        "organization_rejected": (
            "Action required for organization verification",
            "Verification needs attention",
            "Your organization verification needs attention before it can be approved.",
        ),
        "compliance_approved": (
            "Compliance review approved",
            "Compliance approved",
            "Your submitted compliance evidence was approved.",
        ),
        "compliance_rejected": (
            "Action required for compliance review",
            "Compliance review needs attention",
            "Your submitted compliance evidence needs attention before approval.",
        ),
    },
    "tr": {
        "application_submitted": (
            "Yeni ba?vuru al?nd?",
            "Yeni bir ba?vuru ald?n?z",
            "Bir aday f?rsatlar?n?zdan birine ba?vurdu.",
        ),
        "application_interviewing": (
            "M?lakat a?amas?na ge?tiniz",
            "Ba?vurunuz ilerliyor",
            "??veren ba?vurunuzu m?lakat a?amas?na ta??d?.",
        ),
        "application_accepted": (
            "Tebrikler ? ba?vurunuz kabul edildi",
            "Tebrikler!",
            "Ba?vurunuz kabul edildi.",
        ),
        "application_rejected": (
            "Ba?vurunuzla ilgili g?ncelleme",
            "Ba?vurunuz incelendi",
            "??veren ?u anda ba?vurunuzla devam etmeme karar? ald?.",
        ),
        "listing_published": (
            "F?rsat?n?z art?k yay?nda",
            "F?rsat?n?z yay?nland?",
            "F?rsat?n?z incelemeyi ge?ti ve art?k adaylara g?r?n?r durumda.",
        ),
        "listing_changes_requested": (
            "F?rsat?n?z i?in de?i?iklik gerekiyor",
            "F?rsat?n?zda de?i?iklik gerekiyor",
            "L?tfen f?rsat? yeniden g?ndermeden ?nce istenen de?i?iklikleri inceleyin.",
        ),
        "organization_verified": (
            "Kurulu?unuz do?ruland?",
            "Kurulu? do?ruland?",
            "??veren kurulu?u do?rulaman?z onayland?.",
        ),
        "organization_rejected": (
            "Kurulu? do?rulamas? i?in i?lem gerekiyor",
            "Do?rulama dikkat gerektiriyor",
            "Kurulu? do?rulaman?z?n onaylanabilmesi i?in baz? noktalarla ilgilenmeniz gerekiyor.",
        ),
        "compliance_approved": (
            "Uyumluluk incelemesi onayland?",
            "Uyumluluk onayland?",
            "G?nderdi?iniz uyumluluk kan?t? onayland?.",
        ),
        "compliance_rejected": (
            "Uyumluluk incelemesi i?in i?lem gerekiyor",
            "Uyumluluk incelemesi dikkat gerektiriyor",
            "G?nderdi?iniz uyumluluk kan?t?n?n onaylanmadan ?nce g?zden ge?irilmesi gerekiyor.",
        ),
    },
    "ar": {
        "application_submitted": (
            "?? ?????? ??? ????",
            "???? ??? ????",
            "????? ???? ??? ???? ????? ???? ??????.",
        ),
        "application_interviewing": (
            "?????? ??? ????? ????????",
            "???? ?????",
            "??? ???? ????? ???? ??? ????? ????????.",
        ),
        "application_accepted": (
            "??????? ? ?? ???? ????",
            "???????!",
            "?? ???? ????.",
        ),
        "application_rejected": (
            "????? ????? ????",
            "??? ?????? ????",
            "??? ???? ????? ??? ?????? ???? ?? ??? ???????.",
        ),
        "listing_published": (
            "?? ??? ?????",
            "????? ????? ?????",
            "?????? ????? ???????? ?????? ????? ????????.",
        ),
        "listing_changes_requested": (
            "????? ????? ??? ?????",
            "????? ????? ??? ???????",
            "???? ?????? ????????? ???????? ??? ????? ?????? ???????? ??? ????.",
        ),
        "organization_verified": (
            "?? ?????? ?? ??????",
            "?? ?????? ?? ???????",
            "??? ???????? ??? ?????? ?? ????? ???? ?????.",
        ),
        "organization_rejected": (
            "????? ????? ????? ?????? ?? ???????",
            "?????? ????? ??? ??????",
            "????? ????? ?????? ?? ?????? ??? ??? ????????? ??? ???????? ?????.",
        ),
        "compliance_approved": (
            "??? ???????? ??? ?????? ????????",
            "??? ???????? ??? ????????",
            "??? ???????? ??? ??????? ???????? ???? ???????.",
        ),
        "compliance_rejected": (
            "????? ????? ????? ?????? ????????",
            "?????? ???????? ????? ??? ??????",
            "????? ??????? ???????? ???? ??????? ??? ?????? ??? ???????? ?????.",
        ),
    },
}


LABELS = {
    "en": {
        "opportunity": "Opportunity",
        "company": "Company",
        "candidate": "Candidate",
        "feedback": "Reviewer feedback",
        "cta": "Open InternMatch",
        "footer": (
            "This is a transactional message about activity "
            "in your InternMatch AI account."
        ),
    },
    "tr": {
        "opportunity": "F?rsat",
        "company": "?irket",
        "candidate": "Aday",
        "feedback": "?nceleme geri bildirimi",
        "cta": "InternMatch?i A?",
        "footer": (
            "Bu, InternMatch AI hesab?n?zdaki etkinlikle "
            "ilgili i?lemsel bir mesajd?r."
        ),
    },
    "ar": {
        "opportunity": "??????",
        "company": "??????",
        "candidate": "??????",
        "feedback": "??????? ???????",
        "cta": "??? InternMatch",
        "footer": (
            "??? ????? ????? ?????? ????? ????? "
            "?? InternMatch AI."
        ),
    },
}


@dataclass(frozen=True)
class UserEmailDeliveryResult:
    attempted: int
    sent: int


def _data(
    notification: UserNotification,
) -> dict:
    try:
        value = json.loads(
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
        value
        if isinstance(value, dict)
        else {}
    )


def user_email_delivery_configured() -> bool:
    if not bool(
        getattr(
            settings,
            "USER_NOTIFICATION_EMAILS_ENABLED",
            False,
        )
    ):
        return False

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

    return (
        bool(host)
        and bool(from_email)
        and bool(username) == bool(password)
        and security
        in {
            "starttls",
            "ssl",
            "none",
        }
    )


def is_user_notification_email_event(
    *,
    event_type: str,
    data: dict | None = None,
) -> bool:
    if (
        event_type
        not in USER_NOTIFICATION_EMAIL_EVENT_TYPES
    ):
        return False

    if (
        event_type
        != "application_status_changed"
    ):
        return True

    payload = (
        data
        if isinstance(data, dict)
        else {}
    )

    return (
        str(
            payload.get(
                "status",
                "",
            )
        )
        in APPLICATION_EMAIL_STATUSES
    )


def _locale(
    db: Session,
    *,
    user_id: UUID,
) -> str:
    value = db.scalar(
        select(PushDevice.locale)
        .where(
            PushDevice.user_id == user_id,
            PushDevice.enabled.is_(True),
        )
        .order_by(
            PushDevice.updated_at.desc(),
            PushDevice.created_at.desc(),
        )
        .limit(1)
    )

    language = (
        str(value).split("-")[0].lower()
        if value
        else "en"
    )

    return (
        language
        if language in COPY
        else "en"
    )


def _recipient_email(
    user_id: UUID,
) -> str | None:
    supabase_url = (
        settings.SUPABASE_URL
        or ""
    ).strip()

    service_role_key = (
        settings.SUPABASE_SERVICE_ROLE_KEY
        or ""
    ).strip()

    if (
        not supabase_url
        or not service_role_key
    ):
        raise RuntimeError(
            "Supabase service-role configuration "
            "is unavailable for notification email delivery."
        )

    from supabase import create_client

    client = create_client(
        supabase_url,
        service_role_key,
    )

    response = (
        client.auth.admin.get_user_by_id(
            str(user_id)
        )
    )

    user = getattr(
        response,
        "user",
        None,
    )

    if (
        user is None
        and isinstance(
            response,
            dict,
        )
    ):
        user = response.get("user")

    if isinstance(user, dict):
        value = user.get("email")
    else:
        value = getattr(
            user,
            "email",
            None,
        )

    candidate = (
        str(value).strip()
        if value
        else ""
    )

    if (
        not candidate
        or "@" not in candidate
    ):
        return None

    return candidate


def _event_key(
    *,
    event_type: str,
    data: dict,
) -> str:
    if (
        event_type
        == "application_status_changed"
    ):
        return (
            "application_"
            + str(
                data.get(
                    "status",
                    "",
                )
            )
        )

    return event_type


def _context_rows(
    *,
    language: str,
    event_key: str,
    data: dict,
) -> list[tuple[str, str]]:
    labels = LABELS[language]
    rows: list[tuple[str, str]] = []

    values = (
        (
            "opportunity",
            "listing_title",
        ),
        (
            "company",
            "company",
        ),
    )

    for label_key, data_key in values:
        value = str(
            data.get(
                data_key,
                "",
            )
            or ""
        ).strip()

        if value:
            rows.append(
                (
                    labels[label_key],
                    value,
                )
            )

    if (
        event_key
        == "application_submitted"
    ):
        candidate = str(
            data.get(
                "candidate_name",
                "",
            )
            or ""
        ).strip()

        if candidate:
            rows.append(
                (
                    labels["candidate"],
                    candidate,
                )
            )

    if (
        event_key
        == "listing_changes_requested"
    ):
        feedback = str(
            data.get(
                "employer_visible_feedback",
                "",
            )
            or ""
        ).strip()

        if feedback:
            rows.append(
                (
                    labels["feedback"],
                    feedback,
                )
            )

    return rows


def _render(
    notification: UserNotification,
    *,
    language: str,
) -> tuple[str, str, str]:
    data = _data(
        notification
    )

    event_key = _event_key(
        event_type=notification.event_type,
        data=data,
    )

    try:
        subject, heading, body = (
            COPY[language][event_key]
        )
    except KeyError as exc:
        raise ValueError(
            "Unsupported user notification email event."
        ) from exc

    labels = LABELS[language]

    rows = _context_rows(
        language=language,
        event_key=event_key,
        data=data,
    )

    text_lines = [
        heading,
        "",
        body,
    ]

    if rows:
        text_lines.append("")

        for label, value in rows:
            text_lines.append(
                f"{label}: {value}"
            )

    text_lines.extend(
        [
            "",
            labels["cta"],
            PUBLIC_APP_URL,
            "",
            labels["footer"],
        ]
    )

    text_body = "\n".join(
        text_lines
    )

    direction = (
        "rtl"
        if language == "ar"
        else "ltr"
    )

    rows_html = "".join(
        (
            "<tr>"
            '<td style="padding:6px 0;'
            'font-weight:700;color:#334155;">'
            f"{html.escape(label)}</td>"
            '<td style="padding:6px 0 6px 16px;'
            'color:#475569;">'
            f"{html.escape(value)}</td>"
            "</tr>"
        )
        for label, value in rows
    )

    html_body = (
        "<!doctype html>"
        f'<html lang="{language}" dir="{direction}">'
        '<body style="margin:0;padding:0;background:#f4f8f9;'
        "font-family:-apple-system,BlinkMacSystemFont,"
        "'Segoe UI',Arial,sans-serif;color:#0f172a;\">"
        '<table role="presentation" width="100%" '
        'cellspacing="0" cellpadding="0" '
        'style="background:#f4f8f9;padding:24px 12px;">'
        '<tr><td align="center">'
        '<table role="presentation" width="100%" '
        'cellspacing="0" cellpadding="0" '
        'style="max-width:620px;background:#ffffff;'
        'border:1px solid #dce8eb;border-radius:18px;'
        'overflow:hidden;">'
        '<tr><td style="background:#0B5F70;padding:22px 28px;'
        'color:#ffffff;font-size:20px;font-weight:800;">'
        "InternMatch AI"
        "</td></tr>"
        '<tr><td style="padding:30px 28px;">'
        '<h1 style="margin:0 0 14px;font-size:24px;'
        'line-height:1.3;color:#0f172a;">'
        f"{html.escape(heading)}"
        "</h1>"
        '<p style="margin:0 0 18px;font-size:16px;'
        'line-height:1.65;color:#475569;">'
        f"{html.escape(body)}"
        "</p>"
        + (
            '<table role="presentation" width="100%" '
            'cellspacing="0" cellpadding="0" '
            'style="margin:8px 0 24px;">'
            f"{rows_html}</table>"
            if rows_html
            else ""
        )
        + '<a href="'
        + html.escape(
            PUBLIC_APP_URL,
            quote=True,
        )
        + '" style="display:inline-block;background:#0B5F70;'
        'color:#ffffff;text-decoration:none;font-weight:700;'
        'padding:12px 18px;border-radius:10px;">'
        + html.escape(
            labels["cta"]
        )
        + "</a>"
        '<p style="margin:28px 0 0;font-size:12px;'
        'line-height:1.5;color:#94a3b8;">'
        + html.escape(
            labels["footer"]
        )
        + "</p>"
        "</td></tr></table>"
        "</td></tr></table>"
        "</body></html>"
    )

    return (
        subject,
        text_body,
        html_body,
    )


def deliver_user_notification_email(
    db: Session,
    *,
    notification_id: UUID,
) -> UserEmailDeliveryResult:
    notification = db.get(
        UserNotification,
        notification_id,
    )

    if notification is None:
        return UserEmailDeliveryResult(
            attempted=0,
            sent=0,
        )

    data = _data(
        notification
    )

    if not is_user_notification_email_event(
        event_type=notification.event_type,
        data=data,
    ):
        return UserEmailDeliveryResult(
            attempted=0,
            sent=0,
        )

    if not user_email_delivery_configured():
        raise RuntimeError(
            "User notification email delivery "
            "is not configured."
        )

    recipient = _recipient_email(
        notification.recipient_user_id
    )

    if recipient is None:
        return UserEmailDeliveryResult(
            attempted=0,
            sent=0,
        )

    language = _locale(
        db,
        user_id=(
            notification.recipient_user_id
        ),
    )

    subject, text_body, html_body = (
        _render(
            notification,
            language=language,
        )
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

    message["To"] = recipient
    message.set_content(
        text_body
    )

    message.add_alternative(
        html_body,
        subtype="html",
    )

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
            to_addrs=[
                recipient
            ],
        )

    return UserEmailDeliveryResult(
        attempted=1,
        sent=1,
    )
