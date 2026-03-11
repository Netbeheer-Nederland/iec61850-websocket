import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_credentials(full_path: Path) -> list[dict[str, Any]]:
    try:
        with full_path.open(encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            logger.error("Credentials file %s does not contain a JSON list.", full_path)
            return []
        return data
    except FileNotFoundError:
        logger.error("Credentials file not found at %s.", full_path)
    except json.JSONDecodeError:
        logger.error("Credentials file is invalid JSON at %s.", full_path)
    except OSError as error:
        logger.error("Failed reading credentials file %s: %s", full_path, error)
    return []


def save_credentials(full_path: Path, credentials: list[dict[str, Any]]) -> None:
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with full_path.open("w", encoding="utf-8") as file:
            json.dump(credentials, file, indent=4)
    except OSError as error:
        raise OSError(f"Unable to write credentials file {full_path}: {error}") from error
