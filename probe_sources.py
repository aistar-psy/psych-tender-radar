#!/usr/bin/env python3
"""Manually compare public-source reachability from a GitHub Actions runner.

Only public catalog metadata and sanitized response metadata are emitted.
No response body, complete request/redirect URL, exception text, or runner
environment is written to the report.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import time
from urllib import error, request
from urllib.parse import urlsplit

WORKERS = 4
TIMEOUT_SECONDS = 8
MAX_BODY_BYTES = 64 * 1024
ERROR_MESSAGES = {
    "invalid_url": "Target or redirect is not an allowed public HTTP(S) URL.",
    "tls_certificate": "TLS certificate verification failed.",
    "tls": "TLS handshake or protocol failed.",
    "timeout": "Request or response read timed out.",
    "dns": "DNS lookup failed.",
    "connection_refused": "Connection was refused.",
    "connection": "Connection failed or closed unexpectedly.",
    "request": "Request failed; diagnostic details omitted.",
}


def public_url(value):
    """Reject credential-bearing, local, and non-HTTP(S) targets."""
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        raise ValueError("invalid_url")
    parsed = urlsplit(value)
    host = parsed.hostname
    if (parsed.scheme not in ("http", "https") or not host
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("invalid_url")
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise ValueError("invalid_url")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host:
            raise ValueError("invalid_url") from None
    else:
        if not address.is_global:
            raise ValueError("invalid_url")
    # Accessing port also rejects malformed URLs before urllib handles them.
    parsed.port
    return value


class PublicRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def error_category(exc):
    reason = exc.reason if isinstance(exc, error.URLError) else exc
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "tls_certificate"
    if isinstance(reason, ssl.SSLError):
        return "tls"
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(reason, socket.gaierror):
        return "dns"
    if isinstance(reason, ConnectionRefusedError):
        return "connection_refused"
    if isinstance(reason, (ConnectionError, OSError)):
        return "connection"
    if isinstance(reason, ValueError):
        return "invalid_url"
    return "request"


def response_metadata(result, response, target):
    result["http_status"] = int(response.getcode())
    final_url = public_url(response.geturl())
    result["final_host"] = urlsplit(final_url).hostname
    result["redirected"] = final_url != target
    result["redirect_host"] = result["final_host"] if result["redirected"] else None


def probe_source(source):
    started = time.monotonic()
    result = {
        "id": source["id"],
        "name": source["name"],
        "status": "network_error",
        "http_status": None,
        "final_host": None,
        "redirected": False,
        "redirect_host": None,
        "body_bytes_read": 0,
        "body_limit_reached": False,
        "elapsed_ms": 0,
        "error_type": None,
        "error_summary": None,
    }
    try:
        target = public_url(source.get("active_url") or source["url"])
        req = request.Request(target, method="GET", headers={
            "User-Agent": "PsychTenderRadar-SourceProbe/1.0",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.5",
            "Connection": "close",
        })
        opener = request.build_opener(PublicRedirectHandler())
        with opener.open(req, timeout=TIMEOUT_SECONDS) as response:
            response_metadata(result, response, target)
            # Inspect only a small prefix; the body is discarded immediately.
            body = response.read(MAX_BODY_BYTES)
            result["body_bytes_read"] = len(body)
            result["body_limit_reached"] = len(body) == MAX_BODY_BYTES
            del body
            result["status"] = (
                "ok" if 200 <= result["http_status"] < 300 else "http_error"
            )
            if result["status"] == "http_error":
                result["error_type"] = "http"
                result["error_summary"] = f"HTTP {result['http_status']} response."
    except error.HTTPError as exc:
        # HTTP rejection proves a response was received; never read its body.
        try:
            response_metadata(result, exc, target)
        except (ValueError, TypeError):
            result["http_status"] = int(exc.code)
        finally:
            exc.close()
        result["status"] = "http_error"
        result["error_type"] = "http"
        result["error_summary"] = f"HTTP {result['http_status']} response."
    except Exception as exc:
        category = error_category(exc)
        result["status"] = (
            "read_error" if result["http_status"] is not None
            else "invalid_url" if category == "invalid_url"
            else "network_error"
        )
        result["error_type"] = category
        result["error_summary"] = ERROR_MESSAGES[category]
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return result


def load_catalog(path):
    catalog = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(catalog, list):
        raise ValueError("invalid_catalog")
    ids = set()
    for source in catalog:
        if (not isinstance(source, dict)
                or not all(isinstance(source.get(key), str) and source[key]
                           for key in ("id", "name", "url"))
                or source["id"] in ids
                or not isinstance(source.get("domains"), list)):
            raise ValueError("invalid_catalog")
        ids.add(source["id"])
    return catalog


def run_probe(catalog):
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        results = list(executor.map(probe_source, catalog))
    counts = Counter(row["status"] for row in results)
    return {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "workers": WORKERS,
            "timeout_seconds": TIMEOUT_SECONDS,
            "max_body_bytes": MAX_BODY_BYTES,
        },
        "summary": {
            "total": len(results),
            "http_responses": sum(row["http_status"] is not None for row in results),
            "ok": counts["ok"],
            "http_error": counts["http_error"],
            "network_error": counts["network_error"],
            "read_error": counts["read_error"],
            "invalid_url": counts["invalid_url"],
        },
        "results": results,
    }


def summary_text(report):
    s = report["summary"]
    return (
        "Public source reachability comparison\n\n"
        f"Sources: {s['total']}\n"
        f"HTTP responses: {s['http_responses']}\n"
        f"Successful HTTP responses and prefix reads: {s['ok']}\n"
        f"HTTP errors: {s['http_error']}\n"
        f"Network errors: {s['network_error']}\n"
        f"Response read errors: {s['read_error']}\n"
        f"Invalid public URLs: {s['invalid_url']}\n\n"
        "HTTP success does not establish that announcement content is readable.\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog", default=str(Path(__file__).with_name("probe_catalog.json"))
    )
    parser.add_argument("--output", default="source-probe.json")
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
    except (OSError, ValueError, TypeError):
        print("Could not load a valid public probe catalog.", file=sys.stderr)
        return 2
    report = run_probe(catalog)
    try:
        Path(args.output).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        print("Could not write the probe report.", file=sys.stderr)
        return 2
    summary = summary_text(report)
    print(summary)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write(summary)
        except OSError:
            print("Could not append the job summary.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
