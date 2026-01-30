import os
from pathlib import Path

CERT_DIR = Path(os.environ.get("CERT_DIR", Path(__file__).resolve().parents[2] / "testing" / "certs"))
