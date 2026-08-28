"""Build, validate and serialize the Canonical Document envelope."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from galley.document.baseline import block_segments, inline_text
from galley.json_reading import mapping, sequence, text
from galley.validation import load_schema

CANONICAL_SCHEMA_ID = "galley/canonical-document/1"
CANONICAL_SCHEMA, CANONICAL_VALIDATOR = load_schema("canonical-document.json")

TitleSource = Literal["metadata", "filename", "extraction"]
METADATA_TITLE: TitleSource = "metadata"
FILENAME_TITLE: TitleSource = "filename"
EXTRACTION_TITLE: TitleSource = "extraction"

LanguageSource = Literal["metadata", "extraction", "default", "unusable"]
# One value and where it came from, together, because nothing wants one without the other: the
# artifact declares the first and the Report has to state the second beside it.
METADATA_LANGUAGE: LanguageSource = "metadata"
EXTRACTION_LANGUAGE: LanguageSource = "extraction"
DEFAULT_LANGUAGE_SOURCE: LanguageSource = "default"
UNUSABLE_LANGUAGE: LanguageSource = "unusable"
# BCP 47's tag for "not determined". A document nobody stated a language for gets this rather than
# a guess: Galley has not read the words, and `en` would be a claim about a document rather than a
# fact from it. Provisional — no device read has yet reported what CrossPoint does with it.
UNDETERMINED = "und"
# What a language tag can be made of, which is all Galley checks. It does not know which subtags
# exist, so it holds a stated value to the shape a tag takes and lets it through: a source that
# says something outside even that shape would otherwise make the book invalid, which is the
# defect this whole path exists to close. `English` and `xx` therefore pass, and EPUBCheck accepts
# both — correcting them would be a registry Galley carries and a claim about a document it has
# not read. Written out rather than as a pattern because `scripts/checkregex.py` allows no
# production module to import `re`, and this is BCP 47's own grammar rather than a guess about
# one: nothing here is tuned, and there is no threshold to drift.
TAG_CHARACTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
PRIMARY_LENGTHS = range(2, 9)


def canonical_document(
    ast: dict[str, object],
    *,
    title: str,
    author: str | None,
    source_url: str | None,
    warnings: Sequence[dict[str, object]],
) -> dict[str, object]:
    """Wrap one Pandoc AST verbatim in the Galley envelope and validate the result."""

    document: dict[str, object] = {
        "schema": CANONICAL_SCHEMA_ID,
        "title": title,
        "author": author,
        "source_url": source_url,
        "warnings": list(warnings),
        "pandoc": ast,
    }
    validate_canonical_document(document)
    return document


def validate_canonical_document(document: dict[str, object]) -> None:
    """Reject any object outside the Canonical Document schema."""

    CANONICAL_VALIDATOR.validate(document)


def canonical_bytes(document: dict[str, object]) -> bytes:
    """Serialize one validated Canonical Document as the exact persisted bytes."""

    validate_canonical_document(document)
    return f"{json.dumps(document, indent=2, sort_keys=True)}\n".encode()


def canonical_digest(document: dict[str, object]) -> str:
    """Hash the exact bytes the Canonical Document is persisted as."""

    return sha256(canonical_bytes(document)).hexdigest()


def document_title(ast: dict[str, object], *, fallback: str) -> tuple[str, TitleSource]:
    """Take the document's own title, naming the source stem when it states none."""

    stated = meta_text(_meta(ast).get("title"))
    return (stated, METADATA_TITLE) if stated else (fallback, FILENAME_TITLE)


def document_author(ast: dict[str, object]) -> str | None:
    """Take the document's own author, which Markdown may state once or several times."""

    meta = _meta(ast)
    stated = meta_text(meta.get("author")) or meta_text(meta.get("authors"))
    return stated or None


@dataclass(frozen=True)
class DocumentLanguage:
    """The language a book will declare, and which of the four places decided it."""

    value: str
    source: LanguageSource

    @property
    def translations(self) -> str:
        """The language whose strings a writer should look up, which `und` is not one of."""

        return "" if self.value == UNDETERMINED else self.value


def document_language(ast: dict[str, object], *, stated: str | None = None) -> DocumentLanguage:
    """Decide the language the artifact will declare, and say where it came from.

    Never from the packaging environment. Pandoc stamps the ambient locale into `dc:language`
    where nothing states one, so the same source built on two machines carried two languages and
    a machine with no locale configured built an invalid book — `Language tag "C"`, EPUBCheck
    OPF-092. Galley states it explicitly instead, and the writer's fallback never runs.

    Two conventions are read, as `document_author` reads two: `lang` is Pandoc's own metadata key
    and `language` is what an extractor writes into the frontmatter it produces. A value handed in
    by the extractor wins, because on the article route the AST is a parse of content rather than
    of a page and carries no metadata of its own.
    """

    meta = _meta(ast)
    written = meta_text(meta.get("lang")) or meta_text(meta.get("language"))
    candidates: tuple[tuple[str | None, LanguageSource], ...] = (
        (stated, EXTRACTION_LANGUAGE),
        (written, METADATA_LANGUAGE),
    )
    for value, origin in candidates:
        if not value:
            continue
        if _is_language_tag(value):
            return DocumentLanguage(value, origin)
        return DocumentLanguage(UNDETERMINED, UNUSABLE_LANGUAGE)
    return DocumentLanguage(UNDETERMINED, DEFAULT_LANGUAGE_SOURCE)


def _is_language_tag(value: str) -> bool:
    """Say whether a stated value has the shape of a BCP 47 tag, which is all Galley judges."""

    primary, _, _ = value.partition("-")
    return (
        len(primary) in PRIMARY_LENGTHS
        and primary.isalpha()
        and primary.isascii()
        and all(character in TAG_CHARACTERS for character in value)
        and "--" not in value
        and not value.endswith("-")
    )


def meta_text(value: object) -> str:
    """Render one Pandoc metadata value as the plain text a reader would see."""

    node = mapping(value)
    kind = text(node.get("t")) or ""
    content = node.get("c")
    if kind == "MetaString":
        return (text(content) or "").strip()
    if kind == "MetaInlines":
        return inline_text(sequence(content)).strip()
    if kind == "MetaBlocks":
        return " ".join(block_segments(sequence(content))).strip()
    if kind == "MetaList":
        return ", ".join(rendered for item in sequence(content) if (rendered := meta_text(item)))
    return ""


def _meta(ast: dict[str, object]) -> dict[str, object]:
    return mapping(ast.get("meta"))
