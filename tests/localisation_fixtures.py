"""Serve the images a localisation retrieves from loopback, so the gate fetches for real offline.

`localise` is the one command that opens a socket for a Markdown source, and a test that never
opened one would be asserting on a mock of the thing under test. A loopback server gives a real
`http://` locator, a real transport and real failures — a 404, a redirect, an oversize body, bytes
that are not an image — without reaching anything outside this machine.

Loopback is also an address range the command refuses, which is deliberate: the
permitted range is a parameter of the workflow, the command line can only produce `PUBLIC_ONLY`,
and the permissive value exists here and nowhere else. So a successful retrieval is exercised in
this process, and the refusal a real remote-image run would meet is exercised through the
installed CLI, where the hardened value is the only one available.
"""

import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from galley.localisation.workflow import localise_source
from galley.profile.loading import load_profile
from galley.report.envelope import ReportRun
from galley.tools.fetching import LOCAL_PERMITTED
from tests.image_fixtures import grayscale_png

PROFILE = ("--profile", "x4-crosspoint")
ENCODING = "utf-8"


@dataclass(frozen=True)
class Response:
    """One pinned answer this server gives at one path."""

    body: bytes = b""
    status: int = 200
    content_type: str = "image/png"
    location: str | None = None
    """Where a redirect points, which `localise` must refuse to follow rather than obey."""


class _Pinned(ThreadingHTTPServer):
    """A server that knows exactly the resources one document references."""

    resources: dict[str, Response] = {}


class _Handler(BaseHTTPRequestHandler):
    """Answer each pinned path, and treat anything else as genuinely absent."""

    def do_GET(self) -> None:  # noqa: N802 — the name http.server dispatches on.
        pinned = cast(_Pinned, self.server).resources
        answer = pinned.get(self.path, Response(b"not found", 404, "text/plain"))
        self.send_response(answer.status)
        self.send_header("Content-Type", answer.content_type)
        self.send_header("Content-Length", str(len(answer.body)))
        if answer.location is not None:
            self.send_header("Location", answer.location)
        self.end_headers()
        _ = self.wfile.write(answer.body)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the server silent; its output is not part of any test's evidence."""


@contextmanager
def serving(resources: dict[str, Response]) -> Generator[str]:
    """Serve the pinned resources on loopback and yield the origin they are reachable at."""

    server = _Pinned(("127.0.0.1", 0), _Handler)
    server.resources = resources
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def illustrated_source(path: Path, *locators: str, title: str = "An Illustrated Clipping") -> Path:
    """Write a Markdown source whose pictures are remote, as a saved web article's are."""

    pictures = "\n\n".join(
        f"![picture {number}]({locator})" for number, locator in enumerate(locators, start=1)
    )
    _ = path.write_text(
        f"---\ntitle: {title}\nauthor: Ada Lovelace\n---\n\n# {title}\n\n"
        "Prose before the pictures, long enough to read as a document rather than a fragment.\n\n"
        f"{pictures}\n\nProse after the pictures, so the baseline holds words on both sides.\n",
        encoding="utf-8",
    )
    return path


def png_bytes(directory: Path, name: str = "square.png") -> bytes:
    """One small greyscale PNG, as the bytes a pinned response would answer with."""

    return grayscale_png(directory / name).read_bytes()


def localised(source: Path, evidence: Path, *, overwrite: bool = False) -> Any:
    """Run one localisation in this process, against the loopback server a test is serving.

    In this process because the permitted address range is a workflow parameter and the command
    line cannot widen it. Everything else is the command's own code: the same source read, the
    same selection, the same real retrieval, the same Repair Set on disk. The document comes back
    untyped, so a test reads it the same way it reads one parsed off the command line's stdout.
    """

    return localise_source(
        load_profile(PROFILE[1]),
        str(source),
        evidence=evidence,
        overwrite=overwrite,
        permitted=LOCAL_PERMITTED,
        run=ReportRun.start(),
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding=ENCODING))


def file_hashes(directory: Path) -> dict[str, str]:
    """Hash every file below one directory, so a run that wrote outside it can be seen."""

    return {
        str(path.relative_to(directory)): sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def image_locators(document: Any) -> list[str]:
    """Every image `src` the document carries, in the order the walk finds them."""

    def walk(value: Any) -> list[str]:
        if isinstance(value, list):
            return [found for item in cast(list[Any], value) for found in walk(item)]
        if not isinstance(value, dict):
            return []
        node = cast(dict[str, Any], value)
        if node.get("t") == "Image":
            return [str(node["c"][2][0])]
        return [found for item in node.values() for found in walk(item)]

    return walk(document["pandoc"])


def blind_to_image_targets(document: Any) -> str:
    """The document with every image target blanked, so everything else can be compared."""

    def blind(value: Any) -> Any:
        if isinstance(value, list):
            return [blind(item) for item in cast(list[Any], value)]
        if not isinstance(value, dict):
            return value
        node = cast(dict[str, Any], value)
        if node.get("t") == "Image":
            content = cast(list[Any], node["c"])
            return {**node, "c": [content[0], blind(content[1]), ["", content[2][1]]]}
        return {key: blind(item) for key, item in node.items()}

    return json.dumps(blind(document), sort_keys=True)
