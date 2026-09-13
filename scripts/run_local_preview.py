"""Run Vericant locally without connecting to the production database.

Usage from the project root:
    python scripts/run_local_preview.py
    python scripts/run_local_preview.py --port 5051 --show-rollout-banner
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOCAL_DB = ROOT / "instance" / "local-preview.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an isolated local Vericant preview.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--show-rollout-banner", action="store_true")
    args = parser.parse_args()

    LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)

    # Set these before importing the Flask app. Explicit process values take
    # precedence over .env, preventing an accidental production MySQL session.
    os.environ["PA_MYSQL_BUILD_URL"] = "0"
    os.environ["SSH_TUNNEL"] = "0"
    os.environ["DATABASE_URL"] = f"sqlite:///{LOCAL_DB.as_posix()}"
    os.environ["SECRET_KEY"] = "vericant-local-preview-only"
    os.environ["SHOW_ROLLOUT_BANNER"] = "1" if args.show_rollout_banner else "0"

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from app import create_app
    from app.extensions import db

    app = create_app()
    app.config.update(TEMPLATES_AUTO_RELOAD=True)
    with app.app_context():
        db.create_all()

    print(f"Local-only database: {LOCAL_DB}")
    print(f"Preview: http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=True, use_reloader=False)


if __name__ == "__main__":
    main()
