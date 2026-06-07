from __future__ import annotations

from uuid import UUID


ALLOWED_ITEM_TYPES = {"rentable", "consumable", "service", "bundle"}
USER_ROLES = {"admin", "sales", "ops", "finance"}
VALID_QUOTE_STATUSES = {
    "draft",
    "sent",
    "accepted",
    "declined",
    "expired",
    "cancelled",
    "converted",
}


def parse_uuid(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(value))
    except Exception:
        return None


def is_valid_item_type(item_type: str | None) -> bool:
    return bool(item_type) and item_type in ALLOWED_ITEM_TYPES


def is_valid_role(role: str | None) -> bool:
    return bool(role) and role in USER_ROLES


def is_valid_quote_status(status: str | None) -> bool:
    return bool(status) and status in VALID_QUOTE_STATUSES
