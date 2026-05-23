from __future__ import annotations

import requests


def send_notification(message: str, webhook_url: str) -> None:
    response = requests.post(webhook_url, json={"text": message}, timeout=30)
    response.raise_for_status()
