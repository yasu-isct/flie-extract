from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from admission_parser.utils import read_json, sha256_file, write_json


def load_index(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    return read_json(path) if path.exists() else {}


def save_index(path: str | Path, index: dict[str, Any]) -> None:
    write_json(path, index)


def remote_headers(url: str) -> dict[str, str]:
    response = requests.head(url, allow_redirects=True, timeout=30)
    response.raise_for_status()
    return {
        "etag": response.headers.get("ETag", ""),
        "last_modified": response.headers.get("Last-Modified", ""),
    }


def has_remote_change(url: str, index: dict[str, Any]) -> bool:
    headers = remote_headers(url)
    previous = index.get(url, {})
    return headers["etag"] != previous.get("last_etag") or headers["last_modified"] != previous.get("last_modified")


def update_after_download(url: str, pdf_path: str | Path, index: dict[str, Any]) -> bool:
    digest = sha256_file(pdf_path)
    previous = index.get(url, {})
    changed = digest != previous.get("sha256_hash")
    headers = remote_headers(url)
    index[url] = {
        "url": url,
        "last_etag": headers["etag"],
        "last_modified": headers["last_modified"],
        "sha256_hash": digest,
    }
    return changed
