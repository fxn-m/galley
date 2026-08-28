"""Render one preparation transform as the lines a person reads in the terminal.

A transform's name and whether it fired is never the whole story: some destructive transforms
remove working links or repeated captions. A run saying only "fired" hides the decision a reader
is most likely to want to check. Each detail line belongs to the transform that has something to
declare, and a transform with nothing to declare adds none.

Kept beside `render.py` rather than inside it for the same reason `artifact.py` is: one subject
per file, and the Report's terminal rendering has more than one.
"""

from galley.report.quantities import amount, group, nested_amount


def transform_lines(entry: dict[str, object]) -> str:
    """Name one transform, whether it fired, and whatever it has to declare beneath that."""

    state = "fired" if entry["fired"] else "no-op"
    return (
        f"Transform: {entry['name']} ({state})\n"
        f"{_removal_line(entry)}{_caption_line(entry)}{_conversion_line(entry)}"
        f"{_image_line(entry)}{_language_line(entry)}"
    )


def _caption_line(entry: dict[str, object]) -> str:
    """Say how many derived captions stopped being printed, and where those words still are.

    The same reason `_removal_line` exists: this transform takes text off the panel, and "fired"
    on its own leaves a reader unable to check that the copy which went was a duplicate.
    """

    suppressed = amount(entry, "suppressed")
    if not suppressed:
        return ""
    return f"Captions: {suppressed} suppressed, each still printed by the paragraph below it\n"


def _language_line(entry: dict[str, object]) -> str:
    """Name the language the book declares and where it came from.

    A reader has to be able to answer "what language did this book declare?" from the terminal.
    A book declaring `und` may read differently from one declaring a real tag, and this is the
    surface a person actually looks at.
    """

    language = entry.get("language")
    if language is None:
        return ""
    return f"  language {language}, from {entry['language_source']}\n"


def _image_line(entry: dict[str, object]) -> str:
    """Name what happened to the images, since preserved bytes and rewritten ones read alike."""

    resources = amount(entry, "resources")
    if resources is None:
        return ""
    return (
        f"Images: {amount(entry, 'references')} references to {resources} resources, "
        f"{amount(entry, 'preserved')} preserved, {amount(entry, 'normalised')} normalised\n"
    )


def _conversion_line(entry: dict[str, object]) -> str:
    """Name how much back matter one file per note produced, and whether a back-link came with it."""

    documents = amount(entry, "note_documents")
    if documents is None:
        return ""
    backlinks = "with a back-link" if group(entry, "backlinks").get("emitted") else "no back-link"
    return f"Notes: {amount(entry, 'notes')} converted into {documents} documents, {backlinks}\n"


def _removal_line(entry: dict[str, object]) -> str:
    """Name what a destructive transform removed, by kind, rather than only that it ran.

    Link stripping can remove destinations that work on other readers, so a run that says only
    "fired" hides the decision a reader is most likely to want to check.
    """

    kinds = group(entry, "kinds")
    if not kinds:
        return ""
    removed = ", ".join(
        f"{kind} {count}"
        for kind in sorted(kinds)
        if (count := nested_amount(kinds, kind, "removed"))
    )
    classified = nested_amount(entry, "total", "before")
    retained = "; cross-references retained, no Footnote Apparatus recognised"
    interlock = retained if group(entry, "interlock").get("engaged") is True else ""
    return (
        f"Links: {classified} classified; "
        f"{f'destinations removed: {removed}' if removed else 'no destination removed'}"
        f"{interlock}\n"
    )
