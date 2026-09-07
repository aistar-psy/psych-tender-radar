#!/usr/bin/env python3
"""Download only queued public notice URLs; never discover or follow attachments.

The manifest is a JSON array. Successful bodies retain their original bytes and
Content-Type; a download is not a determination of procurement authenticity.
Errors contain fixed categories, never exception messages or environment data.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import tempfile
import time
from urllib import error, request
from urllib.parse import urlsplit
import zlib

WORKERS = 4
TIMEOUT_SECONDS = 10
MAX_BODY_BYTES = 5 * 1024 * 1024
CHUNK_BYTES = 64 * 1024


class FetchFailure(Exception):
    def __init__(self, category):
        self.category = category


def public_url(value, resolve=False):
    if (not isinstance(value, str) or not value
            or any(ord(c) <= 32 for c in value)):
        raise FetchFailure("invalid_url")
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if (parsed.scheme not in ("http", "https") or not host
                or parsed.username is not None or parsed.password is not None
                or host == "localhost"
                or host.endswith((".localhost", ".local", ".internal"))):
            raise FetchFailure("invalid_url")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host:
                raise FetchFailure("invalid_url") from None
        else:
            if not address.is_global:
                raise FetchFailure("non_public_target")
        if resolve:
            addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            if not addresses or any(
                not ipaddress.ip_address(item[4][0]).is_global
                for item in addresses
            ):
                raise FetchFailure("non_public_target")
    except (ValueError, TypeError):
        raise FetchFailure("invalid_url") from None
    return value


class PublicRedirectHandler(request.HTTPRedirectHandler):
    max_redirections = 5

    def __init__(self, deadline):
        super().__init__()
        self.deadline = deadline

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl, resolve=True)
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise FetchFailure("timeout")
        req.timeout = remaining
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def error_type(exc):
    if isinstance(exc, FetchFailure):
        return exc.category
    reason = exc.reason if isinstance(exc, error.URLError) else exc
    if isinstance(reason, FetchFailure):
        return reason.category
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "tls_certificate"
    if isinstance(reason, ssl.SSLError):
        return "tls"
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(reason, socket.gaierror):
        return "dns"
    if isinstance(reason, (ConnectionError, OSError)):
        return "connection"
    return "request_failed"


class PageText(HTMLParser):
    HIDDEN = {"script", "style", "head", "template", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.in_title = False
        self.parts = []
        self.title_parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in self.HIDDEN:
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if not self.hidden:
            self.parts.append(data)


def decoded_text(body, content_type):
    charset = re.search(r"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)", content_type)
    meta = re.search(
        rb"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)", body[:4096], re.I
    )
    encodings = [
        charset.group(1) if charset else "",
        meta.group(1).decode("ascii") if meta else "",
        "utf-8-sig", "gb18030", "big5",
    ]
    for encoding in dict.fromkeys(encodings):
        if not encoding:
            continue
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeError):
            continue
    return body.decode("utf-8", errors="replace")


def pdf_has_text(body):
    """Conservative text-presence check, including common Flate PDF streams."""
    if not body.startswith(b"%PDF-"):
        return False
    budget = 16 * 1024 * 1024
    for match in re.finditer(
        rb"(?:^|[\r\n])stream(?:\r\n|\r|\n)(.*?)(?:\r\n|\r|\n)endstream",
        body, re.S
    ):
        stream = match.group(1)
        if stream.startswith(b"\x78"):
            try:
                stream = zlib.decompressobj().decompress(
                    stream, min(MAX_BODY_BYTES, budget)
                )
            except zlib.error:
                continue
        budget -= len(stream)
        if budget < 0:
            return False
        sample = stream[:4096]
        printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in sample)
        if (sample and printable / len(sample) > 0.85
                and re.search(rb"\bBT\s", stream)
                and re.search(rb"(?:\bTj|\bTJ)\b", stream)):
            return True
    return False


def validate_body(body, content_type):
    if not body or not body.strip():
        raise FetchFailure("no_text")
    media_type = content_type.split(";", 1)[0].strip().lower()
    if body.startswith(b"%PDF-") or media_type == "application/pdf":
        if not pdf_has_text(body):
            raise FetchFailure("pdf_text_unconfirmed")
        return
    if (media_type and not media_type.startswith("text/")
            and media_type not in {
                "application/xhtml+xml", "application/xml", "application/json",
                "application/octet-stream",
            }):
        raise FetchFailure("non_text_content")
    if b"\x00" in body[:8192]:
        raise FetchFailure("non_text_content")
    text = decoded_text(body, content_type)
    raw_lower = text[:100000].lower()
    if any(marker in raw_lower for marker in (
        "window._cf_chl_opt", "/cdn-cgi/challenge-platform/",
        "wzwschallenge", "wzwsquestion",
    )):
        raise FetchFailure("challenge")
    parser = PageText()
    if "html" in media_type or re.match(r"\s*<(?:!doctype|html|head|body)", text, re.I):
        parser.feed(text)
        visible = " ".join(parser.parts)
        title = " ".join(parser.title_parts)
    else:
        visible, title = text, ""
    compact = re.sub(r"\s+", " ", visible).strip()
    lower = compact.lower()
    title = title.lower()
    challenge_markers = (
        "just a moment", "checking your browser", "verify you are human",
        "verify that you are human", "access denied", "security verification",
        "安全验证", "人机验证", "访问验证", "请完成验证", "验证后继续",
        "访问过于频繁", "系统检测到异常访问", "enable javascript",
        "请启用javascript", "请开启javascript",
    )
    if any(m in title for m in challenge_markers) or (
        len(compact) < 1600 and any(m in lower for m in challenge_markers)
    ):
        raise FetchFailure("challenge")
    restricted_markers = (
        "您还没有登录", "以下内容，仅对会员开放", "以下内容仅对会员开放",
        "登录后查看全文", "登陆后查看全文", "请登录后查看正文",
        "sign in to continue", "login required", "authentication required",
        "开通会员可解锁", "付费后查看",
    )
    if any(m in lower for m in restricted_markers):
        raise FetchFailure("access_restricted")
    useful = sum(c.isalnum() for c in compact)
    if useful < 20 or "\ufffd" in compact[:100] and compact.count("\ufffd") > useful:
        raise FetchFailure("no_text")


def read_body(response, deadline):
    encoding = (response.headers.get("Content-Encoding") or "identity").lower()
    if encoding not in ("identity", ""):
        raise FetchFailure("unsupported_content_encoding")
    declared = response.headers.get("Content-Length")
    try:
        declared = int(declared) if declared is not None else None
    except (ValueError, TypeError):
        declared = None
    if declared is not None and declared > MAX_BODY_BYTES:
        raise FetchFailure("body_too_large")
    chunks = []
    size = 0
    eof = False
    while size < MAX_BODY_BYTES:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchFailure("timeout")
        # HTTPResponse.read1 performs at most one underlying buffered read.
        sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
        if sock is not None:
            sock.settimeout(remaining)
        read = getattr(response, "read1", response.read)
        part = read(min(CHUNK_BYTES, MAX_BODY_BYTES - size))
        if not part:
            eof = True
            break
        chunks.append(part)
        size += len(part)
    if size > MAX_BODY_BYTES:
        raise FetchFailure("body_too_large")
    if not eof and size == MAX_BODY_BYTES and (
        declared != size or response.headers.get("Transfer-Encoding")
    ):
        raise FetchFailure("body_limit_reached")
    if declared is not None and declared >= 0 and size != declared:
        raise FetchFailure("incomplete_body")
    return b"".join(chunks)


def save_body(output_dir, body):
    digest = hashlib.sha256(body).hexdigest()
    directory = Path(output_dir) / "downloaded"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (digest + ".bin")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=".notice-", suffix=".tmp", delete=False
        ) as handle:
            temporary = handle.name
            handle.write(body)
        os.replace(temporary, target)
    except OSError:
        if temporary is not None:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass
        raise FetchFailure("storage_error") from None
    return digest, "downloaded/" + digest + ".bin"


def fetch_notice(item, output_dir):
    result = {
        "url": None, "final_url": None, "status": "failed",
        "status_code": None, "content_type": None, "sha256": None,
        "path": None, "error_type": None, "read_at": None,
    }
    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        # Invalid credential-bearing inputs are never repeated in the manifest.
        target = public_url(item["url"])
        result["url"] = target
        public_url(target, resolve=True)
        req = request.Request(target, method="GET", headers={
            "User-Agent": "PsychTenderRadar-PublicNoticeFetch/1.0",
            "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain,*/*;q=0.2",
            "Accept-Encoding": "identity",
            "Connection": "close",
        })
        opener = request.build_opener(PublicRedirectHandler(deadline))
        with opener.open(req, timeout=TIMEOUT_SECONDS) as response:
            result["status_code"] = int(response.getcode())
            result["final_url"] = public_url(response.geturl())
            result["content_type"] = response.headers.get("Content-Type") or ""
            if not 200 <= result["status_code"] < 300:
                raise FetchFailure("http_error")
            body = read_body(response, deadline)
            validate_body(body, result["content_type"])
            result["sha256"], result["path"] = save_body(output_dir, body)
            result["status"] = "ok"
    except error.HTTPError as exc:
        result["status_code"] = int(exc.code)
        result["content_type"] = exc.headers.get("Content-Type") if exc.headers else None
        try:
            result["final_url"] = public_url(exc.geturl())
        except FetchFailure:
            pass
        finally:
            exc.close()
        result["error_type"] = "http_error"
    except Exception as exc:
        result["error_type"] = error_type(exc)
    result["read_at"] = datetime.now(timezone.utc).isoformat()
    return result


def load_queue(path):
    queue = json.loads(Path(path).read_text(encoding="utf-8"))
    if (not isinstance(queue, list)
            or any(not isinstance(row, dict) or not isinstance(row.get("url"), str)
                   for row in queue)):
        raise FetchFailure("invalid_queue")
    return queue


def write_manifest(path, rows):
    path = Path(path)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def run_fetch(queue, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / "manifest.json"
    rows = [None] * len(queue)
    write_manifest(manifest, [])
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        pending = {
            executor.submit(fetch_notice, item, output_dir): index
            for index, item in enumerate(queue)
        }
        for future in as_completed(pending):
            rows[pending[future]] = future.result()
            write_manifest(manifest, [row for row in rows if row is not None])
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default="fetch_queue.json")
    parser.add_argument("--output-dir", default=".")
    args = parser.parse_args(argv)
    try:
        queue = load_queue(args.queue)
        rows = run_fetch(queue, args.output_dir)
    except Exception:
        print("Public notice fetch failed before completion; details omitted.", file=sys.stderr)
        return 2
    ok = sum(row["status"] == "ok" for row in rows)
    summary = (
        f"Public notice downloads: {len(rows)}\n"
        f"Saved with readable text detected: {ok}\n"
        f"Failed or restricted: {len(rows) - ok}\n"
        "The artifact contains only the manifest and successful queued bodies.\n"
    )
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
