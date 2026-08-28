"""Hash a file's bytes the one way every Galley content digest is taken.

Content identity is a SHA-256 over exactly the bytes on disk, and it has to be the same answer
whoever asks. An Inbox Check hashing a source, a publication hashing the book it produced and a
later check asking whether that book is still the one its Report recorded all have to agree, or
`already-ready` would depend on which unit did the arithmetic. Reading in chunks keeps a large
artifact off the heap without changing the answer.
"""

from hashlib import sha256
from pathlib import Path

CHUNK = 1 << 20


def bytes_digest(data: bytes) -> str:
    """Return the SHA-256 of bytes Galley holds rather than bytes on disk.

    A packaged Agent Skill file is read out of the distribution rather than off the filesystem,
    and its digest has to be the same answer `file_digest` gives for the copy that is written
    from it — otherwise an installed skill could never be compared with the one that shipped.
    """

    return sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    """Return the SHA-256 of one file's bytes, reading it a chunk at a time."""

    digest = sha256()
    with path.open("rb") as content:
        while chunk := content.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
