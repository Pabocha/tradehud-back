from typing import Dict, Optional

from comptes.models import UserSettings


ALLOWED_NOTIFICATION_TYPES = {
    "order",
    "promo",
    "message",
    "delivery",
    "product",
    "support",
    "account",
}


def default_notification_preferences() -> Dict[str, bool]:
    return {
        "all": True,
        "order": True,
        "promo": True,
        "message": True,
        "delivery": True,
        "product": True,
        "support": True,
        "account": True,
    }


def normalize_notification_preferences(raw) -> Dict[str, bool]:
    prefs = default_notification_preferences()
    if not isinstance(raw, dict):
        return prefs

    for key in (
        "all",
        "order",
        "promo",
        "message",
        "delivery",
        "product",
        "support",
        "account",
    ):
        value = raw.get(key)
        if isinstance(value, bool):
            prefs[key] = value

    if prefs["all"]:
        for key in ALLOWED_NOTIFICATION_TYPES:
            prefs[key] = True
    else:
        prefs["all"] = all(prefs[key] for key in ALLOWED_NOTIFICATION_TYPES)
    return prefs


def can_receive_notification(user, notification_type: str) -> bool:
    if notification_type == "update_delivery":
        notification_type = "delivery"

    if notification_type not in ALLOWED_NOTIFICATION_TYPES:
        return False

    if not user or not getattr(user, "is_authenticated", False):
        return False

    settings = UserSettings.objects.filter(user=user).first()
    if not settings:
        return True

    if not settings.notifications_enabled:
        return False

    prefs = normalize_notification_preferences(settings.notification_preferences)
    if prefs["all"]:
        return True
    if notification_type == "delivery" and "delivery" not in prefs:
        return bool(prefs.get("update_delivery", True))
    return bool(prefs.get(notification_type, True))


def create_notification_if_allowed(
    *,
    user,
    notification_type: str,
    title: str,
    message: str,
) -> Optional["Notifications"]:
    if not can_receive_notification(user, notification_type):
        return None

    from ecom_app.models import Notifications

    return Notifications.objects.create(
        user=user,
        type=notification_type,
        title=title,
        message=message,
    )
