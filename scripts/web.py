"""Titik masuk Clipper Studio (web UI), bisa dijalankan dari direktori mana pun.

    .venv/bin/python scripts/web.py               -> http://127.0.0.1:8780
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # path relatif (campaigns/, work/) konsisten dengan CLI & MCP

from clipper.web import main  # noqa: E402

if __name__ == "__main__":
    main()
