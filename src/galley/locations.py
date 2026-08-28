"""Name filesystem locations the one way every Report names them."""

from pathlib import Path


def resolved(path: Path) -> Path:
    """Return the stable absolute path Galley identifies one file or directory by.

    Identity is the resolved path, so two names for the same file are one thing. A path that
    cannot be resolved — a broken link, an unreadable parent — still has an absolute form, and
    naming that is more honest than refusing to name it at all.
    """

    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def display_path(path: Path) -> str:
    """Return the stable absolute path Reports use to name a file."""

    return str(resolved(path))
