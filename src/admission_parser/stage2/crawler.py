from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


@dataclass
class UniversityConfig:
    name: str
    research_dept: str
    entry_info_url: str
    pdf_link_selector: str = "a[href$='.pdf']"
    encoding: str = "utf-8"
    delay_seconds: tuple[int, int] = (3, 5)


def robots_allowed(url: str, user_agent: str) -> bool:
    parsed_root = url.split("/", 3)[:3]
    robots_url = "/".join(parsed_root) + "/robots.txt"
    parser = RobotFileParser(robots_url)
    parser.read()
    return parser.can_fetch(user_agent, url)


def discover_pdf_links(config: UniversityConfig, user_agent: str = "AdmissionPDFBot/0.1") -> list[str]:
    if not robots_allowed(config.entry_info_url, user_agent):
        raise PermissionError(f"robots.txt disallows crawling: {config.entry_info_url}")
    time.sleep(config.delay_seconds[0])
    response = requests.get(config.entry_info_url, headers={"User-Agent": user_agent}, timeout=30)
    response.raise_for_status()
    response.encoding = config.encoding
    soup = BeautifulSoup(response.text, "html.parser")
    links = []
    for tag in soup.select(config.pdf_link_selector):
        href = tag.get("href")
        if href and ".pdf" in href.lower():
            links.append(urljoin(config.entry_info_url, href))
    return sorted(set(links))


def download_pdf(url: str, destination: str | Path, user_agent: str = "AdmissionPDFBot/0.1") -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers={"User-Agent": user_agent}, stream=True, timeout=60) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    handle.write(chunk)
    return destination
