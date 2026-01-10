import argparse
from pathlib import Path

import uvicorn

from .web import create_app
from .devcert import ensure_dev_ssl_cert


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
    parser.add_argument("--ssl-keyfile", type=Path, default=None, help="Path to SSL key (enables HTTPS/WSS).")
    parser.add_argument("--ssl-certfile", type=Path, default=None, help="Path to SSL cert (enables HTTPS/WSS).")
    parser.add_argument(
        "--dev-ssl",
        action="store_true",
        help="Generate and use a local dev CA + server cert (self-signed).",
    )
    parser.add_argument(
        "--dev-ssl-host",
        action="append",
        default=[],
        help="Extra DNS names/IPs to include in the dev cert SAN (repeatable).",
    )
    parser.add_argument(
        "--dev-ssl-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".certs",
        help="Output directory for dev certs.",
    )
    args = parser.parse_args(argv)

    app = create_app(static_dir=args.static_dir)

    ssl_keyfile = args.ssl_keyfile
    ssl_certfile = args.ssl_certfile
    if args.dev_ssl:
        certs = ensure_dev_ssl_cert(out_dir=args.dev_ssl_dir, extra_hosts=args.dev_ssl_host)
        ssl_keyfile = certs.server_key
        ssl_certfile = certs.server_cert
        print(f"Dev SSL enabled. Trust this CA on your phone: {certs.ca_cert}")
    elif (ssl_keyfile is None) != (ssl_certfile is None):
        parser.error("--ssl-keyfile and --ssl-certfile must be provided together (or use --dev-ssl).")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        ssl_keyfile=str(ssl_keyfile) if ssl_keyfile else None,
        ssl_certfile=str(ssl_certfile) if ssl_certfile else None,
    )
    return 0
