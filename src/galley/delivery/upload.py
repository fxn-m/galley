"""Send one EPUB to CrossPoint's multipart upload endpoint, and claim nothing about the result.

This is the only request Galley makes that writes. It is deliberately incurious: it reports the
transport status the device gave and whether the request was made at all, and it never turns an
HTTP response into evidence that a book arrived. Confirmation is a fresh destination listing,
which is the caller's job.

The body streams from disk with its length declared up front, so a large book is never held in
memory and CrossPoint receives an ordinary `multipart/form-data` POST. Nothing here asks for
CrossPoint's Optimize action, which Galley does not use and cannot observe.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from galley.delivery.crosspoint import RESPONSE_LIMIT, network_cause, opener
from galley.delivery.targets import DeliveryTarget

UPLOAD_PATH = "/upload"
FIELD_NAME = "file"
CONTENT_TYPE = "application/epub+zip"
CHUNK = 1 << 16


@dataclass(frozen=True)
class Transfer:
    """One upload request: what the device answered, or what stopped the exchange."""

    status: int | None = None
    detail: str = ""


class _Body:
    """A repeatable, length-declaring multipart body streamed from the artifact on disk."""

    def __init__(self, artifact: Path, filename: str, boundary: str) -> None:
        self.artifact = artifact
        self.prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{FIELD_NAME}"; filename="{filename}"\r\n'
            f"Content-Type: {CONTENT_TYPE}\r\n\r\n"
        ).encode()
        self.suffix = f"\r\n--{boundary}--\r\n".encode()
        self.content_length = len(self.prefix) + artifact.stat().st_size + len(self.suffix)

    def __iter__(self) -> Iterator[bytes]:
        yield self.prefix
        with self.artifact.open("rb") as book:
            while chunk := book.read(CHUNK):
                yield chunk
        yield self.suffix


def upload(target: DeliveryTarget, destination: str, artifact: Path) -> Transfer:
    """Make the one writing request, and report only what the exchange itself established."""

    boundary = f"galley-{token_hex(16)}"
    body = _Body(artifact, artifact.name, boundary)
    query = urlencode({"path": destination})
    request = Request(
        f"{target.base_url}{UPLOAD_PATH}?{query}",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(body.content_length),
        },
    )
    try:
        with opener().open(request, timeout=target.timeout_seconds) as response:
            _ = response.read(RESPONSE_LIMIT + 1)
            return Transfer(int(response.status))
    except HTTPError as error:
        return Transfer(int(error.code), f"the device answered {error.code}")
    except (URLError, OSError, ValueError) as error:
        return Transfer(None, network_cause(error))
