import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TIMEOUT = 30  # seconds


def download_pdf(url: str, save_path: str) -> bool:
    """Download a file from *url* to *save_path*.

    Returns True on success, False on HTTP error or exception.
    The destination directory must exist before calling.
    """
    try:
        resp = requests.get(url, timeout=TIMEOUT, stream=True)
        if resp.status_code == 200:
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            logger.info("Downloaded %s → %s", url, save_path)
            return True

        logger.warning("HTTP %s for %s", resp.status_code, url)
        return False

    except requests.RequestException as exc:
        logger.error("Download error for %s: %s", url, exc)
        return False


def get_pdf_path(storage_dir: str, filename: str) -> str:
    """Build the full path where the PDF should be stored."""
    return os.path.join(storage_dir, filename)
