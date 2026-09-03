"""Own source and Default Cover preparation through writer policy, evidence and refusal.

Selection, rendering and resource identity settle here before packaging. The writer receives
one cover instruction; Report records and preservation use the same prepared reference.
SVG composition and dependency-native execution remain in their existing adapters.
"""

from dataclasses import dataclass
from pathlib import Path

from galley.document.baseline import inline_text
from galley.images.default_cover import default_cover_svg
from galley.images.inline import inline_label
from galley.images.references import ImageFailure, ImageReference
from galley.images.resources import ResourcePreparation
from galley.json_reading import mapping, sequence, text
from galley.tools.dependencies import run_dependency
from galley.tools.packaging import CoverImage

DEFAULT_COVER = "default-cover"
SOURCE_COVER = "source-cover-image"
COVER = "cover-image"


@dataclass(frozen=True)
class CoverPreparation:
    """A prepared cover or its failure, with writer settings and Report provenance owned here."""

    reference: ImageReference | None = None
    failure: ImageFailure | None = None
    title: str | None = None
    author: str | None = None

    @property
    def writer(self) -> CoverImage | None:
        if self.reference is None:
            return None
        return CoverImage(self.reference.resource.packaged.path, _cover_template)

    @property
    def facts(self) -> dict[str, object] | None:
        reference = self.reference
        if reference is None:
            return None
        facts: dict[str, object] = {"origin": reference.origin}
        if reference.origin == DEFAULT_COVER:
            facts.update(title=self.title, author=self.author)
        return facts


def prepare_cover(
    ast: dict[str, object],
    resources: ResourcePreparation,
    *,
    title: str,
    author: str | None,
) -> CoverPreparation:
    """Use source cover-image metadata, otherwise compose the profile's Default Cover.

    Resolved source metadata leaves only the working AST, so Pandoc cannot resolve it again
    against a different directory. A Default Cover never enters the AST. Both paths use the
    image pass's resource store, including its origin policy and content-based identity.
    """

    meta = mapping(ast.get("meta"))
    stated = _metadata_text(meta.get(COVER))
    if stated:
        ast["meta"] = {key: value for key, value in meta.items() if key != COVER}
        src, origin = inline_label(stated), SOURCE_COVER
        resource = resources.resolve(stated, COVER)
    else:
        composed = default_cover_svg(title, author, resources.profile)
        if composed is None:
            return CoverPreparation()
        src = origin = DEFAULT_COVER
        resource = resources.hold(composed, DEFAULT_COVER, COVER)
    if isinstance(resource, str):
        return CoverPreparation(failure=ImageFailure(identifier=COVER, src=src, reason=resource))
    return CoverPreparation(
        reference=ImageReference(
            identifier=COVER,
            src=src,
            alt=None,
            title=None,
            resource=resource,
            cover=True,
            origin=origin,
        ),
        title=title if origin == DEFAULT_COVER else None,
        author=author if origin == DEFAULT_COVER else None,
    )


def cover_mismatch(resource: dict[str, object]) -> str | None:
    """A carried cover must be the independently measured OPF cover image."""
    return None if resource.get("cover") is True else "cover-not-declared"


def _metadata_text(value: object) -> str:
    node = mapping(value)
    if text(node.get("t")) == "MetaString":
        return text(node.get("c")) or ""
    return inline_text(sequence(node.get("c"))).strip()


TEMPLATE_ARGUMENT = "--print-default-template=epub3"
TEMPLATE_NAME = "epub3-cover.template"
COVER_BLOCK = "$if(coverpage)$"
BLOCK_END = "$endif$"
OPENED = "<svg"
CLOSED = "</svg>"
IMAGE = "<image"
DIRECT_IMAGE = '<img src="../media/$cover-image$" alt="" />'


def _cover_template(command: str, workspace: Path) -> Path | None:
    """Write Pandoc's own epub3 template with the cover's SVG wrapper replaced by an `img`.

    The alt attribute is empty. A cover carries its title in the image itself, and inventing
    fallback text would make a claim the source never made.
    """

    completed = run_dependency(command, [TEMPLATE_ARGUMENT]).completed
    if completed is None or completed.returncode != 0 or not completed.stdout:
        return None
    patched = _patched(completed.stdout.splitlines())
    destination = workspace / TEMPLATE_NAME
    _ = destination.write_text("\n".join(patched) + "\n", encoding="utf-8")
    return destination


def _patched(lines: list[str]) -> list[str]:
    """Replace the cover block's SVG with a direct image, or leave the template alone.

    Only the conditional cover block is touched, so an SVG anywhere else in the template would
    survive untouched. A template whose cover block holds no SVG needs no patch and is used as
    Pandoc supplied it.
    """

    inside = False
    changed = False
    patched: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == COVER_BLOCK:
            inside = True
        elif inside and stripped == BLOCK_END:
            inside = False
        if not inside or not stripped.startswith((OPENED, CLOSED, IMAGE)):
            patched.append(line)
            continue
        changed = True
        if stripped.startswith(IMAGE):
            patched.append(DIRECT_IMAGE)
    return patched if changed else lines
