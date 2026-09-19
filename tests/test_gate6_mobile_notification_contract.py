
"""Gate 6B mobile notification integration guards."""

import json
from pathlib import Path


def test_expo_notification_native_contract():
    package = json.loads(
        Path(
            "apps/mobile/package.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert (
        "expo-notifications"
        in package["dependencies"]
    )

    app = json.loads(
        Path(
            "apps/mobile/app.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    plugins = app["expo"]["plugins"]

    assert any(
        item == "expo-notifications"
        or (
            isinstance(item, list)
            and item
            and item[0]
            == "expo-notifications"
        )
        for item in plugins
    )


def test_notification_provider_registers_authenticated_device():
    source = Path(
        "apps/mobile/src/context/NotificationContext.js"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "getExpoPushTokenAsync"
        in source
    )

    assert (
        "registerPushDevice"
        in source
    )

    assert (
        "addNotificationReceivedListener"
        in source
    )

    assert (
        "addNotificationResponseReceivedListener"
        in source
    )

    assert (
        "setBadgeCountAsync"
        in source
    )


def test_notification_inbox_and_global_badge_are_wired():
    screen = Path(
        "apps/mobile/src/screens/NotificationsScreen.js"
    ).read_text(
        encoding="utf-8"
    )

    bell = Path(
        "apps/mobile/src/components/NotificationBell.js"
    ).read_text(
        encoding="utf-8"
    )

    header = Path(
        "apps/mobile/src/components/AppChromeHeader.js"
    ).read_text(
        encoding="utf-8"
    )

    app = Path(
        "apps/mobile/App.js"
    ).read_text(
        encoding="utf-8"
    )

    assert "markAllRead" in screen
    assert "refreshNotifications" in screen
    assert "unreadCount" in bell
    assert "<NotificationBell" in header
    assert "<NotificationProvider" in app


def test_notification_localization_exists_in_all_languages():
    for filename in (
        "en.js",
        "ar.js",
        "tr.js",
    ):
        source = Path(
            "apps/mobile/src/localization/locales"
        ).joinpath(
            filename
        ).read_text(
            encoding="utf-8"
        )

        assert "notifications:" in source
        assert "applicationSubmitted" in source
        assert "applicationStatus" in source
        assert "listingPublished" in source
        assert "listingChanges" in source



def test_notification_inbox_actions_are_optimistic_and_swipeable():
    screen = Path(
        "apps/mobile/src/screens/NotificationsScreen.js"
    ).read_text(
        encoding="utf-8"
    )

    context = Path(
        "apps/mobile/src/context/NotificationContext.js"
    ).read_text(
        encoding="utf-8"
    )

    swipe = Path(
        "apps/mobile/src/components/"
        "SwipeableNotificationRow.js"
    ).read_text(
        encoding="utf-8"
    )

    api = Path(
        "apps/mobile/src/services/api.ts"
    ).read_text(
        encoding="utf-8"
    )

    assert "await markRead(" not in screen
    assert "navigation.navigate(" in screen
    assert "markRead(" in screen

    assert "markUnread" in context
    assert "deleteNotification" in context
    assert "reconcileNotificationState" in context

    assert "PanResponder.create" in swipe
    assert "Animated.spring" in swipe
    assert "onToggleRead" in swipe
    assert "onDelete" in swipe

    assert "markNotificationUnread" in api
    assert "deleteUserNotification" in api

    for filename in (
        "en.js",
        "ar.js",
        "tr.js",
    ):
        locale = Path(
            "apps/mobile/src/localization/locales"
        ).joinpath(
            filename
        ).read_text(
            encoding="utf-8"
        )

        assert "markRead:" in locale
        assert "markUnread:" in locale
        assert "delete:" in locale
