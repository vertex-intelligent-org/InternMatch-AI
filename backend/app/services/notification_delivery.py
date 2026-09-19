
"""Expo Push API delivery for durable InternMatch notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import request
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    PushDevice,
    UserNotification,
)

EXPO_PUSH_URL = (
    "https://exp.host/--/api/v2/push/send"
)


@dataclass(frozen=True)
class DeliveryResult:
    attempted: int
    accepted: int
    disabled: int


def _safe_data(
    notification: UserNotification,
) -> dict[str, Any]:
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


def _copy(
    *,
    event_type: str,
    locale: str,
    data: dict[str, Any],
) -> tuple[str, str]:
    language = (
        locale.split("-")[0].lower()
        if locale
        else "en"
    )

    if language not in {
        "ar",
        "tr",
        "en",
    }:
        language = "en"

    status = str(
        data.get(
            "status",
            "",
        )
    )

    company = " ".join(
        str(
            data.get(
                "company",
                "",
            )
            or ""
        ).split()
    )[:80]

    listing_title = " ".join(
        str(
            data.get(
                "title",
                "",
            )
            or ""
        ).split()
    )[:120]

\
    arabic_company_default = (
        "\u0625\u062d\u062f\u0649 "
        "\u0627\u0644\u0634\u0631\u0643\u0627\u062a"
    )

    arabic_title_default = (
        "\u0645\u062a\u062f\u0631\u0628"
    )

    translations = {
        "en": {
            "application_submitted": (
                "New application",
                (
                    "A candidate submitted an application "
                    "to one of your opportunities."
                ),
            ),
            "application_status_changed": (
                "Application updated",
                (
                    "Your application status changed to "
                    f"{status}."
                ),
            ),
            "listing_published": (
                "Opportunity published",
                (
                    "Your opportunity was approved and is "
                    "now visible to candidates."
                ),
            ),
            "new_opportunity_published": (
                "New internship opportunity \U0001f440",
                (
                    f"{company or 'A company'} is looking "
                    f"for {listing_title or 'an intern'}. "
                    "Open InternMatch AI to see if it "
                    "matches you."
                ),
            ),
            "listing_changes_requested": (
                "Changes requested",
                (
                    "Your opportunity needs changes before "
                    "it can be published."
                ),
            ),
            "organization_verified": (
                "Organization verified",
                (
                    "Your employer organization has been "
                    "verified."
                ),
            ),
            "organization_rejected": (
                "Verification update",
                (
                    "Your organization verification needs "
                    "attention."
                ),
            ),
            "compliance_approved": (
                "Compliance approved",
                (
                    "Your submitted compliance evidence "
                    "was approved."
                ),
            ),
            "compliance_rejected": (
                "Compliance update",
                (
                    "Your submitted compliance evidence "
                    "needs attention."
                ),
            ),
        },
        "tr": {
            "application_submitted": (
                "Yeni başvuru",
                (
                    "Bir aday fırsatlarınızdan birine "
                    "başvurdu."
                ),
            ),
            "application_status_changed": (
                "Başvuru güncellendi",
                (
                    "Başvurunuzun durumu "
                    f"{status} olarak değişti."
                ),
            ),
            "listing_published": (
                "Fırsat yayınlandı",
                (
                    "Fırsatınız onaylandı ve artık "
                    "adaylara görünür."
                ),
            ),
            "new_opportunity_published": (
                "Yeni staj f\u0131rsat\u0131 \U0001f440",
                (
                    f"{company or 'Bir \u015firket'}, "
                    f"{listing_title or 'bir stajyer'} "
                    "ar\u0131yor. Sana uygun olup olmad\u0131\u011f\u0131n\u0131 "
                    "g\u00f6rmek i\u00e7in InternMatch AI'\u0131 a\u00e7."
                ),
            ),
            "listing_changes_requested": (
                "Değişiklik istendi",
                (
                    "Fırsatınız yayınlanmadan önce "
                    "değişiklik gerekiyor."
                ),
            ),
            "organization_verified": (
                "Kuruluş doğrulandı",
                (
                    "İşveren kuruluşunuz doğrulandı."
                ),
            ),
            "organization_rejected": (
                "Doğrulama güncellemesi",
                (
                    "Kuruluş doğrulamanızla ilgilenmeniz "
                    "gerekiyor."
                ),
            ),
            "compliance_approved": (
                "Uyumluluk onaylandı",
                (
                    "Gönderdiğiniz uyumluluk kanıtı "
                    "onaylandı."
                ),
            ),
            "compliance_rejected": (
                "Uyumluluk güncellemesi",
                (
                    "Gönderdiğiniz uyumluluk kanıtıyla "
                    "ilgilenmeniz gerekiyor."
                ),
            ),
        },
        "ar": {
            "application_submitted": (
                "طلب جديد",
                (
                    "قدّم مرشح طلباً على إحدى فرصك."
                ),
            ),
            "application_status_changed": (
                "تم تحديث الطلب",
                (
                    "تغيّرت حالة طلبك إلى "
                    f"{status}."
                ),
            ),
            "listing_published": (
                "تم نشر الفرصة",
                (
                    "تمت الموافقة على فرصتك وأصبحت "
                    "ظاهرة للمرشحين."
                ),
            ),
            "new_opportunity_published": (
                (
                    "\u0641\u0631\u0635\u0629 "
                    "\u062a\u062f\u0631\u064a\u0628 "
                    "\u062c\u062f\u064a\u062f\u0629 "
                    "\U0001f440"
                ),
                (
                    f"{company or arabic_company_default} "
                    "\u062a\u0628\u062d\u062b \u0639\u0646 "
                    f"{listing_title or arabic_title_default}. "
                    "\u0627\u0641\u062a\u062d InternMatch AI "
                    "\u0648\u0634\u0648\u0641 \u0625\u0630\u0627 "
                    "\u0627\u0644\u0641\u0631\u0635\u0629 "
                    "\u0645\u0646\u0627\u0633\u0628\u0629 "
                    "\u0625\u0644\u0643."
                ),
            ),
            "listing_changes_requested": (
                "مطلوب تعديلات",
                (
                    "تحتاج فرصتك إلى تعديلات قبل "
                    "أن يتم نشرها."
                ),
            ),
            "organization_verified": (
                "تم توثيق المؤسسة",
                (
                    "تم توثيق مؤسسة صاحب العمل "
                    "الخاصة بك."
                ),
            ),
            "organization_rejected": (
                "تحديث التوثيق",
                (
                    "يحتاج طلب توثيق مؤسستك "
                    "إلى مراجعتك."
                ),
            ),
            "compliance_approved": (
                "تمت الموافقة على الامتثال",
                (
                    "تمت الموافقة على مستندات "
                    "الامتثال المقدمة."
                ),
            ),
            "compliance_rejected": (
                "تحديث الامتثال",
                (
                    "تحتاج مستندات الامتثال "
                    "المقدمة إلى مراجعتك."
                ),
            ),
        },
    }

    default = {
        "en": (
            "InternMatch AI update",
            "There is a new update for your account.",
        ),
        "tr": (
            "InternMatch AI güncellemesi",
            "Hesabınız için yeni bir güncelleme var.",
        ),
        "ar": (
            "تحديث من InternMatch AI",
            "يوجد تحديث جديد لحسابك.",
        ),
    }

    return translations[
        language
    ].get(
        event_type,
        default[language],
    )


def _message(
    *,
    notification: UserNotification,
    device: PushDevice,
) -> dict[str, Any]:
    data = _safe_data(
        notification
    )

    title, body = _copy(
        event_type=notification.event_type,
        locale=device.locale,
        data=data,
    )

    payload_data: dict[str, Any] = {
        "notification_id": str(
            notification.id
        ),
        "event_type":
            notification.event_type,
    }

    if notification.entity_type:
        payload_data[
            "entity_type"
        ] = notification.entity_type

    if notification.entity_id:
        payload_data[
            "entity_id"
        ] = str(
            notification.entity_id
        )

    # Only explicit user-facing routing metadata is copied
    # into the push payload. Internal/admin-only fields never
    # cross this transport boundary.
    for key in (
        "application_id",
        "internship_id",
        "organization_id",
        "claim_id",
        "status",
    ):
        value = data.get(
            key
        )

        if value is not None:
            payload_data[key] = str(
                value
            )

    return {
        "to": device.expo_push_token,
        "title": title,
        "body": body,
        "sound": "default",
        "channelId": "general",
        "data": payload_data,
    }


def deliver_notification(
    db: Session,
    *,
    notification_id: UUID,
) -> DeliveryResult:
    notification = db.get(
        UserNotification,
        notification_id,
    )

    if notification is None:
        return DeliveryResult(
            attempted=0,
            accepted=0,
            disabled=0,
        )

    devices = list(
        db.scalars(
            select(PushDevice)
            .where(
                PushDevice.user_id
                == notification.recipient_user_id,
                PushDevice.enabled.is_(True),
            )
            .order_by(
                PushDevice.created_at.asc()
            )
        ).all()
    )

    if not devices:
        return DeliveryResult(
            attempted=0,
            accepted=0,
            disabled=0,
        )

    messages = [
        _message(
            notification=notification,
            device=device,
        )
        for device in devices
    ]

    body = json.dumps(
        messages,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode(
        "utf-8"
    )

    req = request.Request(
        EXPO_PUSH_URL,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type":
                "application/json",
            "Accept-Encoding":
                "gzip, deflate",
        },
        method="POST",
    )

    with request.urlopen(
        req,
        timeout=10,
    ) as response:
        raw = response.read()

    parsed = json.loads(
        raw.decode("utf-8")
    )

    tickets = parsed.get(
        "data",
        [],
    )

    if not isinstance(
        tickets,
        list,
    ):
        raise RuntimeError(
            "Expo Push API returned an invalid "
            "ticket payload."
        )

    accepted = 0
    disabled = 0

    for index, device in enumerate(
        devices
    ):
        ticket = (
            tickets[index]
            if index < len(tickets)
            else {}
        )

        if not isinstance(
            ticket,
            dict,
        ):
            continue

        if (
            ticket.get("status")
            == "ok"
        ):
            accepted += 1
            continue

        details = ticket.get(
            "details"
        )

        error_code = (
            details.get("error")
            if isinstance(
                details,
                dict,
            )
            else None
        )

        if (
            error_code
            == "DeviceNotRegistered"
        ):
            device.enabled = False
            disabled += 1

    db.flush()

    return DeliveryResult(
        attempted=len(devices),
        accepted=accepted,
        disabled=disabled,
    )
