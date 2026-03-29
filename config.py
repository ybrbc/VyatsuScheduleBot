import json
import os

REQUIRED_KEYS = ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "GROUP_ID", "ADMIN_ID"]
OPTIONAL_KEYS = ["SES1", "SES2"]
SECRETS_FILENAME = "secrets.json"


def load_secrets():
    if os.path.exists(SECRETS_FILENAME):
        with open(SECRETS_FILENAME, 'r') as f:
            secrets = json.load(f)
            for key in REQUIRED_KEYS:
                if key not in secrets or not secrets[key]:
                    raise ValueError(f"Missing key: {key}")
    else:
        raise FileNotFoundError("Fill secrets.json")

    return secrets