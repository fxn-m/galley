"""Name a Ready Artifact deterministically, and never let two different books share a name.

The first distinct artifact for a title takes that title's name. Different bytes competing for
it take a short suffix of their own hash — deterministic, so the same book gets the same name
whatever order the Workspace was filled in, and never an order-dependent `-2`. Bytes already
published under a name are reused rather than rewritten, because a Ready Artifact is immutable
and rewriting it with a copy of itself would be a window in which it did not exist.
"""

import unicodedata
from dataclasses import dataclass
from pathlib import Path

from galley.digests import file_digest
from galley.output.publication import Collision, Publication

ARTIFACT_SUFFIX = ".epub"
HASH_LENGTH = 12
NAME_LIMIT = 80
FALLBACK_NAME = "book"
SEPARATOR = "-"
PORTABLE_PUNCTUATION = "'’(),[]&-_"


@dataclass(frozen=True)
class ReadyOutput:
    """The Ready directory one preparation would publish an immutable artifact into."""

    directory: Path

    def publication_for(self, candidate: Path, title: str) -> Publication | Collision:
        """Choose this candidate's Ready Artifact path from its own name and its own bytes.

        The base name is tried first, then the hash-suffixed name. Either one already holding
        these exact bytes is reused; the suffixed name holding different bytes is a genuine
        digest-prefix clash and is refused rather than resolved, because overwriting it would
        destroy a published artifact.
        """

        digest = file_digest(candidate)
        base = artifact_base(title)
        preferred = self.directory / f"{base}{ARTIFACT_SUFFIX}"
        if not preferred.exists():
            return Publication(preferred)
        if file_digest(preferred) == digest:
            return Publication(preferred, reuse=True)
        digest_suffix = f"{SEPARATOR}{digest[:HASH_LENGTH]}"
        collision_base = _truncate(base, NAME_LIMIT - len(digest_suffix)).rstrip(" .")
        distinct = self.directory / f"{collision_base}{digest_suffix}{ARTIFACT_SUFFIX}"
        if not distinct.exists():
            return Publication(distinct)
        existing = file_digest(distinct)
        if existing == digest:
            return Publication(distinct, reuse=True)
        return Collision(distinct, existing, digest)


def artifact_base(title: str) -> str:
    """Take a human-readable file name from the name the Canonical Document already settled.

    That name is the document's own title, or its source stem where the document states none, so
    there is nothing left to invent here. What survives is letters, numbers and common portable
    punctuation,
    because the name has to work as a filename on the reading device as well as in a Workspace.
    """

    return _slug(title) or FALLBACK_NAME


def _slug(value: str) -> str:
    normalised = unicodedata.normalize("NFC", value)
    words = "".join(
        character if character.isalnum() or character in f"{PORTABLE_PUNCTUATION}." else " "
        for character in normalised
    ).split()
    return _truncate(" ".join(words), NAME_LIMIT).strip(" .")


def _truncate(value: str, byte_limit: int) -> str:
    used = 0
    for index, character in enumerate(value):
        used += len(character.encode("utf-8"))
        if used > byte_limit:
            return value[:index]
    return value
