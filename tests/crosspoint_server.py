"""Serve CrossPoint's own HTTP surface from loopback, so no gate reaches a real device.

Delivery is transport, and transport is only proven by speaking it. This server answers the
three endpoints CrossPoint exposes — status, destination listing and multipart upload — from
127.0.0.1, which is a trusted Delivery target, so the installed CLI performs a genuine request,
a genuine listing and a genuine confirmation against pinned responses.

Nothing here is a stand-in for Galley's own code: the tests drive the installed subprocess and
observe this server's recorded state, never Galley's transport internals.
"""

import json
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import urlsplit

STATUS_PATH = "/api/status"
FILES_PATH = "/api/files"
UPLOAD_PATH = "/upload"
X4_STATUS: dict[str, object] = {
    "device": "X4",
    "version": "1.4.1",
    "mode": "File Transfer",
    "storage": {"free": 1234567},
}


@dataclass
class Device:
    """One pinned CrossPoint device: what it says it is, and what it currently holds."""

    status: object = field(default_factory=lambda: dict(X4_STATUS))
    files: dict[str, int] = field(default_factory=dict[str, int])
    status_delay_seconds: float = 0.0
    status_disconnects: int = 0
    listing_disconnects: int = 0
    upload_delay_seconds: float = 0.0
    redirect_paths: tuple[str, ...] = ()
    malformed_paths: tuple[str, ...] = ()
    # Listings that must pass before an accepted upload becomes visible, which is how a device
    # that has written the bytes but not yet listed them is reproduced without timing.
    visibility_delay: int = 0
    # A device whose listing only becomes unreadable once bytes have been sent, which is the
    # one way a post-write confirmation can fail that a pre-write listing cannot show.
    listing_malformed_after_upload: bool = False
    upload_status: int = 200
    upload_requests: int = 0
    listing_requests: int = 0
    uploads: list[tuple[str, int]] = field(default_factory=list[tuple[str, int]])
    upload_content_types: list[str] = field(default_factory=list[str])
    upload_queries: list[str] = field(default_factory=list[str])
    pending: list[tuple[str, int, int]] = field(default_factory=list[tuple[str, int, int]])

    def accept(self, name: str, byte_size: int) -> None:
        """Store one uploaded file, after as many listings as this device delays visibility."""

        self.uploads.append((name, byte_size))
        if self.visibility_delay <= 0:
            self.files[name] = byte_size
            return
        self.pending.append((name, byte_size, self.visibility_delay))

    def release(self) -> None:
        """Count down every delayed upload by one listing, revealing those that reach zero."""

        still: list[tuple[str, int, int]] = []
        for name, byte_size, remaining in self.pending:
            if remaining <= 1:
                self.files[name] = byte_size
            else:
                still.append((name, byte_size, remaining - 1))
        self.pending = still

    def listed(self) -> list[dict[str, object]]:
        """Render the destination listing in CrossPoint's own shape."""

        return [
            {"name": name, "size": size, "isDirectory": False}
            for name, size in sorted(self.files.items())
        ]


class _CrossPointServer(ThreadingHTTPServer):
    """A server backed by exactly one pinned device."""

    device: Device = Device()

    def handle_error(self, request: object, client_address: object) -> None:
        """Stay silent when a client that timed out has already closed the socket.

        A timeout test deliberately abandons the exchange mid-response, and the resulting
        broken pipe is the expected shape of that test rather than a fault to report.
        """


class _Handler(BaseHTTPRequestHandler):
    """Answer status, listing and upload the way CrossPoint 1.4.1 answers them."""

    protocol_version = "HTTP/1.1"

    @property
    def device(self) -> Device:
        """Read the pinned device this handler answers for."""

        return cast(_CrossPointServer, self.server).device

    def do_GET(self) -> None:  # noqa: N802 — the name http.server dispatches on.
        route = urlsplit(self.path)
        if self._diverted(route.path):
            return
        if route.path == STATUS_PATH:
            if self.device.status_disconnects:
                self.device.status_disconnects -= 1
                self.close_connection = True
                return
            time.sleep(self.device.status_delay_seconds)
            self._json(self.device.status)
            return
        if route.path == FILES_PATH:
            self.device.listing_requests += 1
            if self.device.listing_disconnects:
                self.device.listing_disconnects -= 1
                self.close_connection = True
                return
            if self.device.listing_malformed_after_upload and self.device.upload_requests:
                self._respond(b"<html>not json</html>", "application/json", 200)
                return
            listed = self.device.listed()
            self.device.release()
            self._json(listed)
            return
        self._respond(b"not found", "text/plain", 404)

    def do_POST(self) -> None:  # noqa: N802 — the name http.server dispatches on.
        route = urlsplit(self.path)
        if route.path != UPLOAD_PATH:
            self._respond(b"not found", "text/plain", 404)
            return
        self.device.upload_requests += 1
        self.device.upload_queries.append(route.query)
        self.device.upload_content_types.append(self.headers.get("Content-Type") or "")
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        time.sleep(self.device.upload_delay_seconds)
        if self._diverted(route.path):
            return
        stored = _multipart(body)
        if stored is not None and self.device.upload_status < 400:
            self.device.accept(*stored)
        if self.device.upload_status >= 400:
            self._respond(b"refused", "text/plain", self.device.upload_status)
            return
        if UPLOAD_PATH in self.device.malformed_paths:
            self._respond(b"<html>not json</html>", "application/json", 200)
            return
        self._json({"ok": True})

    def _diverted(self, path: str) -> bool:
        """Answer the shapes a healthy device never produces, when a test pinned one."""

        if path in self.device.redirect_paths:
            body = b"moved"
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            _ = self.wfile.write(body)
            return True
        if path in self.device.malformed_paths:
            self._respond(b"<html>not json</html>", "application/json", 200)
            return True
        return False

    def _json(self, payload: object) -> None:
        self._respond(json.dumps(payload).encode("utf-8"), "application/json", 200)

    def _respond(self, body: bytes, content_type: str, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        _ = self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the server silent; its output is not part of any test's evidence."""


def _multipart(body: bytes) -> tuple[str, int] | None:
    """Read the one part CrossPoint is sent: its declared filename and its exact byte count."""

    head, separator, rest = body.partition(b"\r\n\r\n")
    marker = b'filename="'
    start = head.find(marker)
    end = head.find(b'"', start + len(marker))
    if not separator or start < 0 or end < 0:
        return None
    closing = rest.rfind(b"\r\n--")
    if closing < 0:
        return None
    return head[start + len(marker) : end].decode("utf-8"), len(rest[:closing])


@contextmanager
def crosspoint(device: Device | None = None) -> Generator[tuple[str, Device]]:
    """Serve one pinned CrossPoint on loopback and yield its `HOST:PORT` and its state."""

    pinned = device if device is not None else Device()
    server = _CrossPointServer(("127.0.0.1", 0), _Handler)
    server.device = pinned
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"127.0.0.1:{server.server_address[1]}", pinned
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
