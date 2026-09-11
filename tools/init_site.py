#!/usr/bin/env python3
import sys
from pathlib import Path


project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "app" / "shared"))

from site_store import DATABASE_PATH, initialize, list_articles  # noqa: E402


initialize()
print("Website database:", DATABASE_PATH)
print("Articles:", len(list_articles()))
