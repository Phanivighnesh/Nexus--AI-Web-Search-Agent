"""
run.py
─────────────────────────────────────────────────────────────────
Entry point for the NEXUS AI Web Search Agent.

Development:
    python run.py

Production (gunicorn):
    gunicorn "run:create_app()" -w 2 -b 0.0.0.0:7860 --timeout 120
─────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app

# Module-level app instance — required by Vercel's @vercel/python
app = create_app()

if __name__ == "__main__":
    from app.config import get_settings
    settings = get_settings()
    app.run(
        host=settings.flask_host,
        port=settings.flask_port,
        debug=settings.flask_debug,
        use_reloader=False,
    )

