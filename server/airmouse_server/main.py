import argparse
from pathlib import Path

import uvicorn

from .web import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AirMouse server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--static-dir",
        type=Path,
        default=None,
        help="Directory containing the built web client (Next.js export).",
    )
    args = parser.parse_args(argv)

    app = create_app(static_dir=args.static_dir)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0

