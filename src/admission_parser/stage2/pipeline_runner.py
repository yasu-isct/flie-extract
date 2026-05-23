from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from admission_parser.pipeline import parse_pdf
from admission_parser.stage2.crawler import UniversityConfig, discover_pdf_links, download_pdf
from admission_parser.stage2.db_manager import Database
from admission_parser.stage2.update_detector import load_index, save_index, update_after_download
from admission_parser.utils import sha256_file

LOGGER = logging.getLogger(__name__)


def run(config_path: str | Path, db_path: str | Path = "data/admissions.sqlite3") -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    configs = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))["universities"]
    db = Database(db_path)
    db.init()
    index_path = Path("data/update_index.json")
    index = load_index(index_path)

    for raw_config in configs:
        try:
            config = UniversityConfig(
                name=raw_config["name"],
                research_dept=raw_config["research_dept"],
                entry_info_url=raw_config["entry_info_url"],
                pdf_link_selector=raw_config.get("pdf_link_selector", "a[href$='.pdf']"),
                encoding=raw_config.get("encoding", "utf-8"),
                delay_seconds=tuple(raw_config.get("delay_seconds", [3, 5])),
            )
            LOGGER.info("Checking %s %s", config.name, config.research_dept)
            university_id = db.upsert_university(
                config.name,
                config.research_dept,
                config.entry_info_url,
                raw_config,
            )
            for url in discover_pdf_links(config):
                destination = Path("downloads") / config.name / Path(url).name
                download_pdf(url, destination)
                if not update_after_download(url, destination, index):
                    LOGGER.info("No content change: %s", url)
                    continue
                output = Path("outputs") / config.name / f"{destination.stem}.json"
                payload = parse_pdf(destination, output=output)
                year = payload.get("university", {}).get("admission_year")
                db.upsert_admission_entry(university_id, year, payload, sha256_file(destination))
                LOGGER.info("Parsed and stored: %s", output)
        except Exception as exc:
            LOGGER.exception("Failed processing %s: %s", raw_config.get("name"), exc)
    save_index(index_path, index)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/universities.yaml")
    parser.add_argument("--db", default="data/admissions.sqlite3")
    args = parser.parse_args()
    run(args.config, args.db)


if __name__ == "__main__":
    main()
