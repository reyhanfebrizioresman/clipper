"""Titik masuk server MCP clipper, bisa dijalankan dari direktori mana pun
(mis. lewat `ssh reyhan .../python .../scripts/mcp_server.py`)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # path relatif (campaigns/, work/) konsisten dengan CLI

from clipper.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
