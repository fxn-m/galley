"""Serve pinned Article-Like Page responses from loopback, so no gate reaches the internet.

Defuddle owns URL retrieval, so a behavioural article test needs a real `http://` locator rather
than a file path. A loopback server answering fixed bytes gives one: the retrieval, extraction and
parse are all real, and the response is as pinned as a committed fixture file. The dependency
stand-ins here cover only the shapes a real page and a real tool cannot produce.
"""

import json
import subprocess
import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from tests.article_fixtures import ARTICLE, ARTICLE_PATH, ENCODING


class _PinnedServer(ThreadingHTTPServer):
    """A server that knows exactly one page and the resources that page references."""

    page: str = ARTICLE_PATH
    document: str = ""
    resources: dict[str, bytes] = {}


class _Handler(BaseHTTPRequestHandler):
    """Answer the page at its own path, and any pinned resource the page references."""

    @property
    def pinned(self) -> _PinnedServer:
        """Read the server this handler answers for, which knows one page and its resources."""

        return cast(_PinnedServer, self.server)

    def do_GET(self) -> None:  # noqa: N802 — the name http.server dispatches on.
        resource = self.pinned.resources.get(self.path)
        if resource is not None:
            self._respond(resource, "application/octet-stream", 200)
            return
        if self.path != self.pinned.page:
            # Anything this server was not given is genuinely absent, so a reference to it fails
            # the way a reference to a removed image fails on the real web.
            self._respond(b"not found", "text/plain", 404)
            return
        self._respond(self.pinned.document.encode(ENCODING), f"text/html; charset={ENCODING}", 200)

    def _respond(self, body: bytes, content_type: str, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        _ = self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the server silent; its output is not part of any test's evidence."""


@contextmanager
def served(
    document: str = ARTICLE,
    *,
    path: str = ARTICLE_PATH,
    resources: dict[str, bytes] | None = None,
) -> Generator[str]:
    """Serve one pinned response on loopback and yield the URL that retrieves it.

    `resources` pins the bytes the page's own references resolve to, so an illustrated article
    is as reproducible as a plain one and still reaches nothing outside this machine.
    """

    server = _PinnedServer(("127.0.0.1", 0), _Handler)
    server.document = document
    server.page = path
    server.resources = resources or {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}{path}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def extracted_content(url: str) -> str:
    """Extract one URL with the same pinned Defuddle, independently of Galley."""

    completed = subprocess.run(
        ["defuddle", "parse", url, "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return str(json.loads(completed.stdout)["content"])


# A stand-in that answers the version probe and then writes something that is not a Defuddle
# document. Malformed dependency output cannot be induced from a real page, so this is the one
# extraction shape a recorded process result is the honest way to reach.
MALFORMED_DEFUDDLE = """#!/bin/sh
if [ "$1" = "--version" ]; then printf '0.19.1\\n'; exit 0; fi
printf 'not a defuddle document' > "$5"
exit 0
"""


def write_command(path: Path, script: str) -> Path:
    """Write one executable dependency stand-in and return the command path."""

    _ = path.write_text(script, encoding=ENCODING)
    path.chmod(0o755)
    return path


def defuddle_returning(path: Path, content: str) -> Path:
    """Write a stand-in extractor that returns one chosen content document.

    Defuddle deduplicates repeated endnote identifiers itself, so a duplicate target cannot be
    reached through the real tool from any page. A recorded process result is the only honest way
    to exercise the recovery condition that guards against one.
    """

    document = json.dumps(
        {"content": content, "title": "A Chosen Extraction", "author": "", "wordCount": 0}
    )
    script = (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if sys.argv[1] == '--version':\n"
        "    print('0.19.1')\n"
        "    raise SystemExit(0)\n"
        f"open(sys.argv[5], 'w', encoding='utf-8').write({document!r})\n"
    )
    return write_command(path, script)


def native_html_ast(content: str, workspace: Path) -> Any:
    """Parse extracted content with the same pinned Pandoc reader, independently of Galley."""

    source = workspace / "independent.html"
    _ = source.write_text(content, encoding=ENCODING)
    completed = subprocess.run(
        ["pandoc", "--from", "html", "--to", "json", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def write_html(path: Path, text: str = ARTICLE) -> Path:
    """Write one pinned response to disk, for tests about local files rather than retrieval."""

    _ = path.write_text(text, encoding=ENCODING)
    return path
