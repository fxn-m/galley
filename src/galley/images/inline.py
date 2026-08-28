"""Read the bytes an inline `data:` reference carries, and name it in something a Report can hold.

An extractor turning a page's inline `<svg>` furniture into an `<img>` produces a reference whose
payload *is* the resource: no host, no path, no retrieval. So this is the narrowest resolution
Galley performs — it opens no socket and reads no file — and it is a fact about the format rather
than about any one site.

The other half of the subject is length. A base64 payload runs to thousands of characters, and a
Report that pasted one into a refusal summary or an image record would be unreadable and unbounded
at once. `inline_label` is the one name such a reference is reported under, everywhere.
"""

from base64 import b64decode
from binascii import Error as BinasciiError
from typing import Literal
from urllib.parse import unquote_to_bytes

SCHEME = "data:"
BASE64_MARKER = ";base64"
# What is kept of the part before the payload. It carries the media type the document claimed and
# whether the payload is base64, which is everything a reader needs to recognise the reference;
# the payload itself is identified by the reference id and the digest already in the record.
LABEL_LIMIT = 60
ELISION = ",…"

InlineReason = Literal["malformed-inline-reference", "undecodable-inline-data"]


def is_inline(src: str) -> bool:
    """Say whether one reference carries its own bytes rather than naming somewhere to get them."""

    return src.strip().lower().startswith(SCHEME)


def inline_label(src: str) -> str:
    """The bounded name an inline reference is reported under, and the only one.

    Any other reference is its own name: a path or a locator is already something a reader can
    act on, and shortening it would take that away.
    """

    if not is_inline(src):
        return src
    prefix, separator, _ = src.strip().partition(",")
    if not separator:
        return prefix[:LABEL_LIMIT]
    return prefix[:LABEL_LIMIT] + ELISION


def inline_bytes(src: str) -> bytes | InlineReason:
    """The bytes one inline reference carries, or the reason it carries none.

    Two failures rather than one, because they are different mistakes: a reference with no comma
    is not a data URI at all, while one whose payload will not decode is a data URI carrying
    something that is not what it says. Bytes that decode but are not an image are neither — the
    ordinary measurement answers that, under the reason it already has.
    """

    prefix, separator, payload = src.strip().partition(",")
    if not separator:
        return "malformed-inline-reference"
    if not prefix.lower().endswith(BASE64_MARKER):
        return unquote_to_bytes(payload)
    try:
        return b64decode("".join(payload.split()), validate=True)
    except BinasciiError, ValueError:
        return "undecodable-inline-data"
