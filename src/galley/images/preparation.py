"""Resolve the images a Canonical Document references, and hand the writer bytes Galley measured.

Preparation preserves compatible fitting bytes, normalises everything else, and remeasures every
referenced resource rather than trusting its label. All of that starts here: Galley
resolves each reference itself and points the writer at a file it wrote, so the resource in the
finished book is the resource that was measured — not a second file some other resolver found
under the same relative name.

Every reference keeps a stable id, and resources are identified by their content. Two references
to one image therefore share one packaged resource without anything having to notice they came
from the same path.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from galley.document.baseline import inline_text
from galley.json_reading import mapping, sequence, text
from galley.images.inline import inline_label
from galley.images.normalisation import ImageRule, image_rule
from galley.images.resources import (
    PRESERVED,
    PackagedResource,
    ResourceOrigin,
    packaged_resource,
)

IMAGE = "Image"
NOTE = "Note"
IMAGE_STAGE = "image-preparation"
SRCSET = "srcset"
SIZES = "sizes"
RESPONSIVE = (SRCSET, SIZES)
COVER = "cover-image"


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


@dataclass(frozen=True)
class ImageFailure:
    """One reference preparation could not carry into the book, and why.

    `src` is the reference as reported, on the same terms as `ImageReference.src`.
    """

    identifier: str
    src: str
    reason: str


@dataclass(frozen=True)
class ImagePreparation:
    """One image pass: the working copy it produced and every reference it resolved or refused."""

    ast: dict[str, object]
    references: list[ImageReference] = field(default_factory=list[ImageReference])
    resources: list[PackagedResource] = field(default_factory=list[PackagedResource])
    failures: list[ImageFailure] = field(default_factory=list[ImageFailure])
    cover: ImageReference | None = None

    @property
    def preserved(self) -> int:
        return sum(1 for resource in self.resources if resource.transform == PRESERVED)

    @property
    def normalised(self) -> int:
        return len(self.resources) - self.preserved


@dataclass
class _Pass:
    """State one walk accumulates: the profile's rule, where files come from and where they go."""

    profile: dict[str, object]
    rule: ImageRule
    origin: ResourceOrigin
    workspace: Path
    references: list[ImageReference] = field(default_factory=list[ImageReference])
    failures: list[ImageFailure] = field(default_factory=list[ImageFailure])
    resources: dict[str, PackagedResource] = field(default_factory=dict[str, PackagedResource])

    def identifier(self) -> str:
        return f"image-{len(self.references) + len(self.failures) + 1}"

    def resolved(self, src: str, name: str) -> PackagedResource | str:
        """Package one reference's bytes, reusing a resource whose content is already packaged."""

        resource = packaged_resource(
            src,
            profile=self.profile,
            rule=self.rule,
            origin=self.origin,
            workspace=self.workspace,
            name=name,
        )
        if isinstance(resource, str):
            return resource
        held = self.resources.setdefault(resource.digest, resource)
        return held


def prepare_images(
    ast: dict[str, object], *, profile: dict[str, object], origin: ResourceOrigin, workspace: Path
) -> ImagePreparation:
    """Resolve, measure and package every image this document references, in reading order.

    The cover is prepared through the same path as any other reference, because it is one: the
    Canonical Document's own metadata names it, with no separate encoding rule.
    """

    state = _Pass(profile=profile, rule=image_rule(profile), origin=origin, workspace=workspace)
    working = cast(dict[str, object], _value(ast, state))
    cover = _cover(working, state)
    return ImagePreparation(
        ast=working,
        references=state.references,
        resources=list(state.resources.values()),
        failures=state.failures,
        cover=cover,
    )


def _cover(ast: dict[str, object], state: _Pass) -> ImageReference | None:
    """Prepare the cover image the document's metadata names, if it names one.

    The metadata entry is removed from the working copy once it is resolved. Pandoc reads
    `cover-image` itself and would resolve the same relative name a second time, against the
    process it runs in rather than against the document; preparation states the resolved file to
    the writer instead, so one resolver decides which bytes are the cover.
    """

    meta = mapping(ast.get("meta"))
    stated = _metadata_text(meta.get(COVER))
    if not stated:
        return None
    ast["meta"] = {key: value for key, value in meta.items() if key != COVER}
    resource = state.resolved(stated, COVER)
    label = inline_label(stated)
    if isinstance(resource, str):
        state.failures.append(ImageFailure(identifier=COVER, src=label, reason=resource))
        return None
    reference = ImageReference(
        identifier=COVER, src=label, alt=None, title=None, resource=resource, cover=True
    )
    state.references.append(reference)
    return reference


def _metadata_text(value: object) -> str:
    """Read one metadata value as the plain string it renders to, whatever Pandoc wrapped it in."""

    node = mapping(value)
    if text(node.get("t")) == "MetaString":
        return text(node.get("c")) or ""
    return inline_text(sequence(node.get("c"))).strip()


def _value(value: object, state: _Pass) -> object:
    """Rebuild one AST value, resolving each `Image` wherever in the structure it sits.

    An image's own description is not walked. Pandoc copies a figure's caption inlines into it,
    so the description is a second copy of text that is already reachable, and it can hold no
    image of its own.
    """

    if isinstance(value, list):
        return [_value(item, state) for item in cast(list[object], value)]
    if not isinstance(value, dict):
        return value
    node = cast(dict[str, object], value)
    if text(node.get("t")) == IMAGE:
        return _image(node, state)
    return {key: _value(item, state) for key, item in node.items()}


def _image(node: dict[str, object], state: _Pass) -> dict[str, object]:
    """Resolve one reference, and point it at the bytes preparation packaged for it."""

    content = sequence(node.get("c"))
    target = sequence(_at(content, 2))
    src = text(_at(target, 0)) or ""
    title = text(_at(target, 1)) or ""
    identifier = state.identifier()
    resource = state.resolved(src, identifier)
    label = inline_label(src)
    if isinstance(resource, str):
        state.failures.append(ImageFailure(identifier=identifier, src=label, reason=resource))
        return node
    attributes, candidates = _responsive(_at(content, 0))
    state.references.append(
        ImageReference(
            identifier=identifier,
            src=label,
            alt=_described(sequence(_at(content, 1))) or None,
            title=title or None,
            resource=resource,
            candidates=candidates,
        )
    )
    # The packaged file's name, not its path. The name is chosen by reading order and is the same
    # on every run; the directory it sits in is a fresh temporary one, and putting that in the AST
    # made `packaged_ast_sha256` different on every run over identical inputs. Packaging resolves
    # the name against the working copy with `--resource-path`.
    return {**node, "c": [attributes, _at(content, 1), [resource.packaged.path.name, title]]}


def _responsive(attributes: object) -> tuple[list[object], list[str]]:
    """Record the `srcset` candidates and remove them, keeping the already-resolved `src`.

    Galley does not implement browser candidate selection in 0.1.0, and Pandoc packages only the
    `src`: leaving `srcset` behind would name candidate files the archive does not carry, which
    is EPUBCheck-invalid as well as untrue.
    """

    values = sequence(attributes)
    pairs = sequence(_at(values, 2))
    candidates = [
        stripped
        for pair in pairs
        if text(_at(sequence(pair), 0)) == SRCSET
        for candidate in (text(_at(sequence(pair), 1)) or "").split(",")
        if (stripped := candidate.strip())
    ]
    kept = [pair for pair in pairs if text(_at(sequence(pair), 0)) not in RESPONSIVE]
    return [_at(values, 0), _at(values, 1), kept], candidates


def _described(inlines: list[object]) -> str:
    """Render one image's description as the alt text the finished book will carry.

    A figure's caption inlines are copied into the description, notes included, and Pandoc's
    writer flattens the description to `alt` while dropping the note. Rendering a note's body
    here would record alt text the artifact never carries and make an exact-preservation claim
    false.
    """

    return inline_text(sequence(_visible(inlines))).strip()


def _visible(value: object) -> object:
    """Drop the `Note` inlines from one description, keeping every other value as it stands."""

    if isinstance(value, list):
        return [
            _visible(item)
            for item in cast(list[object], value)
            if text(mapping(item).get("t")) != NOTE
        ]
    if not isinstance(value, dict):
        return value
    return {key: _visible(item) for key, item in cast(dict[str, object], value).items()}


def _at(content: object, index: int) -> object:
    values = sequence(content)
    return values[index] if index < len(values) else None
