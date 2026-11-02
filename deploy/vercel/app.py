"""ASGI entrypoint for the Vercel Python runtime."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
os.environ.setdefault("STREAMLIT_SERVER_MAX_UPLOAD_SIZE", "10")

import streamlit as st

app = st.App(ROOT / "dashboard_entry.py")
