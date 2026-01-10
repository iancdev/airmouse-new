from __future__ import annotations

import ipaddress
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DevCertPaths:
    ca_cert: Path
    ca_key: Path
    server_cert: Path
    server_key: Path


def _guess_default_ipv4() -> str | None:
    # Uses routing table selection without actually sending packets.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        return ip
    except OSError:
        return None
    finally:
        sock.close()


def _san_value(hosts: list[str]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for host in hosts:
        h = host.strip()
        if not h:
            continue
        if h in seen:
            continue
        seen.add(h)
        try:
            ipaddress.ip_address(h)
            parts.append(f"IP:{h}")
        except ValueError:
            parts.append(f"DNS:{h}")
    return ",".join(parts)


def _run_openssl(args: list[str]) -> None:
    try:
        subprocess.run(["openssl", *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("openssl not found. Install OpenSSL (or mkcert) to enable HTTPS.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"openssl failed: {stderr or exc}") from exc


def ensure_dev_ssl_cert(
    *,
    out_dir: Path,
    extra_hosts: list[str] | None = None,
    days: int = 3650,
) -> DevCertPaths:
    out_dir.mkdir(parents=True, exist_ok=True)

    ca_key = out_dir / "airmouse-ca-key.pem"
    ca_cert = out_dir / "airmouse-ca-cert.pem"
    server_key = out_dir / "airmouse-server-key.pem"
    server_cert = out_dir / "airmouse-server-cert.pem"
    server_csr = out_dir / "airmouse-server.csr"

    if ca_key.exists() and ca_cert.exists() and ca_key.stat().st_size > 0 and ca_cert.stat().st_size > 0:
        pass
    else:
        _run_openssl(
            [
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-sha256",
                "-days",
                str(days),
                "-nodes",
                "-keyout",
                str(ca_key),
                "-out",
                str(ca_cert),
                "-subj",
                "/CN=AirMouse Dev CA",
                "-addext",
                "basicConstraints=critical,CA:TRUE,pathlen:0",
                "-addext",
                "keyUsage=critical,digitalSignature,keyCertSign,cRLSign",
            ]
        )

    hosts: list[str] = ["localhost", "127.0.0.1"]
    if extra_hosts:
        hosts.extend(extra_hosts)
    if (ip := _guess_default_ipv4()) is not None:
        hosts.append(ip)
    san = _san_value(hosts)

    needs_server = not (
        server_key.exists()
        and server_cert.exists()
        and server_key.stat().st_size > 0
        and server_cert.stat().st_size > 0
    )
    if needs_server:
        _run_openssl(
            [
                "req",
                "-newkey",
                "rsa:2048",
                "-sha256",
                "-nodes",
                "-keyout",
                str(server_key),
                "-out",
                str(server_csr),
                "-subj",
                "/CN=AirMouse",
            ]
        )

        ext = "\n".join(
            [
                "basicConstraints=CA:FALSE",
                "keyUsage=critical,digitalSignature,keyEncipherment",
                "extendedKeyUsage=serverAuth",
                f"subjectAltName={san}",
                "",
            ]
        )
        with tempfile.NamedTemporaryFile("w", delete=False, dir=out_dir, prefix="airmouse-ext-", suffix=".cnf") as f:
            ext_path = Path(f.name)
            f.write(ext)

        try:
            _run_openssl(
                [
                    "x509",
                    "-req",
                    "-in",
                    str(server_csr),
                    "-CA",
                    str(ca_cert),
                    "-CAkey",
                    str(ca_key),
                    "-CAcreateserial",
                    "-out",
                    str(server_cert),
                    "-days",
                    str(days),
                    "-sha256",
                    "-extfile",
                    str(ext_path),
                ]
            )
        finally:
            try:
                ext_path.unlink(missing_ok=True)
            except Exception:
                pass

    return DevCertPaths(ca_cert=ca_cert, ca_key=ca_key, server_cert=server_cert, server_key=server_key)

