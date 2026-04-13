#!/usr/bin/env python3
"""Download the CERT Insider Threat Test Dataset.

The CERT dataset is available from CMU's kilthub repository. This script
attempts to download and extract the relevant files (logon, http, email).

If automatic download fails, it prints instructions for manual download
and the generate_data.py script will fall back to synthetic generation.
"""

import io
import os
import sys
import zipfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

KILTHUB_URL = (
    "https://kilthub.cmu.edu/ndownloader/articles/12841247/versions/1"
)

EXPECTED_FILES = ["logon.csv", "http.csv", "email.csv"]


def download_cert():
    """Download CERT dataset from CMU kilthub."""
    config.CERT_RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Check if already downloaded
    existing = [f for f in EXPECTED_FILES if (config.CERT_RAW_DIR / f).exists()]
    if len(existing) == len(EXPECTED_FILES):
        print(f"CERT data already present in {config.CERT_RAW_DIR}")
        return True

    print("Attempting to download CERT Insider Threat dataset from CMU kilthub...")
    print(f"URL: {KILTHUB_URL}")

    try:
        import urllib.request

        req = urllib.request.Request(
            KILTHUB_URL,
            headers={"User-Agent": "DataLakeDemo/1.0"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()

        # Try to extract as zip
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for name in zf.namelist():
                    basename = os.path.basename(name)
                    if basename in EXPECTED_FILES:
                        print(f"  Extracting {basename}...")
                        with zf.open(name) as src:
                            (config.CERT_RAW_DIR / basename).write_bytes(
                                src.read()
                            )

            extracted = [
                f for f in EXPECTED_FILES if (config.CERT_RAW_DIR / f).exists()
            ]
            if extracted:
                print(f"Successfully extracted {len(extracted)} files.")
                return len(extracted) == len(EXPECTED_FILES)

        print("Download succeeded but format was unexpected.")
        return False

    except Exception as e:
        print(f"Automatic download failed: {e}")
        return False


def print_manual_instructions():
    """Print instructions for manual CERT dataset download."""
    print(
        f"""
===============================================================================
MANUAL DOWNLOAD REQUIRED
===============================================================================

The CERT Insider Threat Test Dataset could not be downloaded automatically.
You can obtain it from either source:

  1. CMU kilthub (official):
     https://kilthub.cmu.edu/articles/dataset/Insider_Threat_Test_Dataset/12841247

  2. Kaggle (community mirror):
     https://www.kaggle.com/datasets/nitishabharathi/cert-insider-threat

After downloading, place these files in:
  {config.CERT_RAW_DIR}/

Required files:
  - logon.csv
  - http.csv
  - email.csv

Then re-run: make generate-data

NOTE: If you skip this step, generate_data.py will create synthetic security
data based on the CERT schema. The demo works either way.
===============================================================================
"""
    )


def main():
    success = download_cert()
    if not success:
        print_manual_instructions()
        sys.exit(1)
    print("CERT dataset ready.")


if __name__ == "__main__":
    main()
