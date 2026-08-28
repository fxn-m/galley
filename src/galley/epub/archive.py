"""Read EPUB archive members without modifying the audited subject."""

from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import unquote, urlsplit
from zipfile import BadZipFile, ZipFile

ReferenceKind = Literal["in-book", "external", "same-document", "unsafe"]
UnreadableReason = Literal["missing", "not-a-regular-file", "not-a-zip-archive", "unreadable"]


class ArchiveError(Exception):
    """The audited archive could not be opened for reading."""

    def __init__(self, reason: UnreadableReason, detail: str) -> None:
        super().__init__(detail)
        self.reason: UnreadableReason = reason
        self.detail = detail


class EpubArchive:
    """One opened EPUB archive exposing read-only member facts."""

    def __init__(self, archive: ZipFile) -> None:
        self._archive = archive
        self._names = tuple(info.filename for info in archive.infolist())
        self._known = frozenset(self._names)
        self._unreadable: set[str] = set()

    @property
    def names(self) -> frozenset[str]:
        """Name every member the archive declares, without duplicates."""

        return self._known

    @property
    def member_count(self) -> int:
        """Count every member entry the archive declares, duplicates included."""

        return len(self._names)

    @property
    def duplicate_members(self) -> list[str]:
        """Name every member the archive declares more than once."""

        counts = Counter(self._names)
        return sorted(name for name, count in counts.items() if count > 1)

    @property
    def unsafe_members(self) -> list[str]:
        """Name every member whose stored name escapes the archive root."""

        return [name for name in self._names if is_unsafe_member(name)]

    @property
    def unreadable_members(self) -> list[str]:
        """Name every declared member a read attempt could not decode."""

        return sorted(self._unreadable)

    def contains(self, name: str) -> bool:
        """Report whether the archive declares one exact member name."""

        return name in self._known

    def read(self, name: str) -> bytes | None:
        """Return one member's bytes, or None when it is absent or unreadable."""

        if name not in self._known:
            return None
        try:
            return self._archive.read(name)
        except BadZipFile, OSError, RuntimeError, ValueError:
            self._unreadable.add(name)
            return None

    def read_text(self, name: str) -> str | None:
        """Return one member decoded as UTF-8 with replacement characters."""

        data = self.read(name)
        return None if data is None else data.decode("utf-8", errors="replace")


def open_archive(path: Path) -> ZipFile:
    """Open one EPUB archive read-only or raise a classified ArchiveError."""

    try:
        return ZipFile(path)
    except BadZipFile as error:
        raise ArchiveError("not-a-zip-archive", str(error)) from error
    except OSError as error:
        raise ArchiveError(unreadable_reason(error), str(error)) from error


def unreadable_reason(error: OSError) -> UnreadableReason:
    """Classify why one path could not be read as an archive."""

    if isinstance(error, FileNotFoundError):
        return "missing"
    if isinstance(error, IsADirectoryError):
        return "not-a-regular-file"
    return "unreadable"


def is_unsafe_member(name: str) -> bool:
    """Report whether an archive member name escapes or evades the archive root."""

    if not name or name.startswith("/") or "\\" in name:
        return True
    return ".." in PurePosixPath(name).parts


def normalise_archive_path(value: str) -> str | None:
    """Normalise one archive-root-relative path, rejecting escapes."""

    return join_archive_path("", value)


def join_archive_path(base: str, relative: str) -> str | None:
    """Resolve one relative path against a member's directory within the archive."""

    candidate = (
        PurePosixPath(relative.lstrip("/"))
        if relative.startswith("/")
        else PurePosixPath(base).parent / relative
    )
    parts: list[str] = []
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            _ = parts.pop()
            continue
        parts.append(part)
    return "/".join(parts) if parts else None


def classify_reference(base: str, href: str) -> tuple[ReferenceKind, str | None]:
    """Classify one document reference and resolve in-book targets to member names."""

    target = href.strip()
    if not target or target.startswith("#"):
        return "same-document", None
    split = urlsplit(target)
    if split.scheme or split.netloc:
        return "external", None
    path_part = target.split("#", 1)[0]
    if not path_part:
        return "same-document", None
    resolved = join_archive_path(base, unquote(path_part))
    if resolved is None:
        return "unsafe", None
    return "in-book", resolved
