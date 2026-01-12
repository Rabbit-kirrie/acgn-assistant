from __future__ import annotations

import os
import sys
from pathlib import Path

# Vercel Python runtime runs from the project root.
# Our package lives under ./src, so ensure it's importable.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Optional: default ENV to prod on Vercel unless explicitly overridden.
os.environ.setdefault("ENV", os.environ.get("VERCEL_ENV") or "prod")

from acgn_assistant.main import create_app  # noqa: E402

app = create_app()
