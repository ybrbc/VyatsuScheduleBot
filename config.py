import json
import os
import logging

logger = logging.getLogger(__name__)

SECRETS_FILE = os.path.join(os.path.dirname(__file__), "secrets.json")

REQUIRED_KEYS = ["TELEGRAM_TOKEN", "DATABASE_URL"]


def load_secrets() -> dict:
    if not os.path.exists(SECRETS_FILE):
        raise FileNotFoundError(
            f"secrets.json not found. Copy secrets.json.example → secrets.json and fill it in."
        )
    with open(SECRETS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for key in REQUIRED_KEYS:
        if key not in data or not data[key]:
            raise ValueError(f"Missing required config key: {key}")

    # Backward compat: single ADMIN_ID → ADMIN_IDS list
    if "ADMIN_IDS" not in data:
        old = data.get("ADMIN_ID", [])
        data["ADMIN_IDS"] = old if isinstance(old, list) else [str(old)]

    # Backward compat: TELEGRAM_CHAT_ID → ADMIN_CHAT_ID
    if "ADMIN_CHAT_ID" not in data:
        data["ADMIN_CHAT_ID"] = data.get("TELEGRAM_CHAT_ID", "")

    # Backward compat: single GROUP_ID → GROUPS list
    if "GROUPS" not in data and "GROUP_ID" in data:
        data["GROUPS"] = [{"id": str(data["GROUP_ID"]), "name": str(data["GROUP_ID"]), "active": True}]

    data.setdefault("GROUPS", [])
    data.setdefault("BASE_URL", "https://neuroslopppn.kozow.com/static/Group/")
    data.setdefault("BASE_SES_URL", "https://neuroslopppn.kozow.com/static/Ses/")
    data.setdefault("SES1", "")
    data.setdefault("SES2", "")

    return data


SECRETS = load_secrets()
