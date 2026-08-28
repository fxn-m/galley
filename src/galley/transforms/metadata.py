"""State what preparation told the writer about the document itself.

Title, author and language are one subject and a different one from the transforms beside them:
each is a fact about the document handed to the writer as metadata, rather than a Device Profile
activation acting on the content. Each content transform records the second kind beside its own
implementation.

Three transforms because each decides something different, and one of them decides not to fire.
A document that states no author leaves the package with no creator, and that is a decision this
run records rather than a step whose silence could equally mean it is broken. The language always
fires: Pandoc's own default for it is the packaging machine's locale, so leaving it unstated is
not an option this project has — it built a different book on every machine and an invalid one
wherever no locale was configured.
"""

from typing import cast

from galley.document.canonical import (
    DEFAULT_LANGUAGE_SOURCE,
    EXTRACTION_LANGUAGE,
    METADATA_LANGUAGE,
    UNUSABLE_LANGUAGE,
    DocumentLanguage,
    LanguageSource,
)
from galley.profile.loading import activation_entry
from galley.report.quantities import reported

DOCUMENT_TITLE = "document-title"
DOCUMENT_AUTHOR = "document-author"
DOCUMENT_LANGUAGE = "document-language"
NAVIGATION_DEPTH = "navigation-depth"
TOC_DEPTH = "toc_depth"
# Why the artifact declares the language it declares. Pandoc's own answer is the packaging
# machine's locale, so every one of these is Galley refusing that answer rather than improving it.
LANGUAGE_NOTES: dict[LanguageSource, str] = {
    METADATA_LANGUAGE: "The document states its own language, which is passed to the writer.",
    EXTRACTION_LANGUAGE: (
        "The extractor read a language from the page, which is passed to the writer."
    ),
    DEFAULT_LANGUAGE_SOURCE: (
        "Nothing states this document's language, so the artifact declares BCP 47 `und` — "
        "undetermined. Galley has not read the words and states no language it was not given."
    ),
    UNUSABLE_LANGUAGE: (
        "A language was stated and is not shaped like a BCP 47 tag, so the artifact declares "
        "`und` rather than a value the format would reject."
    ),
}

TITLE_NOTE = (
    "The Canonical Document's own title is stated to the writer. Pandoc emits no dc:title for a "
    "document that carries none, which is an EPUB3 conformance error, so a title is always "
    "stated even where it came from the source filename rather than the source's metadata."
)
AUTHOR_STATED = "The Canonical Document states an author, which is passed to the writer."
AUTHOR_ABSENT = (
    "The Canonical Document states no author, so none was passed to the writer and the package "
    "claims no creator. Nothing was invented for the metadata the source did not carry."
)
NAVIGATION_NOTE = (
    "The Device Profile's navigation depth is passed to packaging as the generated "
    "table-of-contents depth. The profile records no device-judged Reading Quality for this "
    "value, so Galley applies it without claiming a reader has confirmed it."
)
NAVIGATION_ABSENT = (
    "This Device Profile activates no navigation depth, so none was passed to packaging and the "
    "writer's own default stands. Galley states no depth it did not get from profile data."
)


def navigation_transform(profile: dict[str, object], depth: int | None) -> dict[str, object]:
    """State the navigation depth preparation applied, and the activation it came from."""

    entry = activation_entry(profile, TOC_DEPTH)
    return {
        "name": NAVIGATION_DEPTH,
        "fired": depth is not None,
        "activation": TOC_DEPTH,
        "device_judged": entry.get("device_judged") is True,
        "justified_by": entry.get("justified_by"),
        "depth": None if depth is None else reported(depth, "levels"),
        "note": NAVIGATION_NOTE if depth is not None else NAVIGATION_ABSENT,
    }


def metadata_transforms(
    document: dict[str, object], canonical: dict[str, object], language: DocumentLanguage
) -> list[dict[str, object]]:
    """State the title, author and language handed to the writer, and where each came from."""

    author = cast(str | None, document["author"])
    return [
        {
            "name": DOCUMENT_TITLE,
            "fired": True,
            "title": document["title"],
            "title_source": canonical["title_source"],
            "note": TITLE_NOTE,
        },
        {
            "name": DOCUMENT_AUTHOR,
            "fired": author is not None,
            "author": author,
            "note": AUTHOR_STATED if author is not None else AUTHOR_ABSENT,
        },
        {
            "name": DOCUMENT_LANGUAGE,
            "fired": True,
            "language": language.value,
            "language_source": language.source,
            "note": LANGUAGE_NOTES[language.source],
        },
    ]
