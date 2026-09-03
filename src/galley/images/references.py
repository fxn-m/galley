"""Prepared image references and failures retain source identity independently of resources."""

from dataclasses import dataclass, field

from galley.images.resources import PackagedResource


@dataclass(frozen=True)
class ImageReference:
    """One Canonical Document image reference, with the identity it keeps through the Report.

    `src` is the reference **as reported**, which is the locator itself for everything except an
    inline `data:` reference, where it is the bounded name `images/inline.py` gives one. The field
    keeps the Report's own key rather than a truer name, because that key is the schema's; what a
    reader gets is a line they can act on instead of a thousand characters of base64.
    """

    identifier: str
    src: str
    alt: str | None
    title: str | None
    resource: PackagedResource
    candidates: list[str] = field(default_factory=list[str])
    """The `srcset` candidates removed after recording them, if the source offered any."""
    cover: bool = False
    origin: str | None = None


@dataclass(frozen=True)
class ImageFailure:
    """One reference preparation could not carry into the book, and why.

    `src` is the reference as reported, on the same terms as `ImageReference.src`.
    """

    identifier: str
    src: str
    reason: str
