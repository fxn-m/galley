"""Take the SVG wrapper out of Pandoc's cover page, using Pandoc's own template.

The X4 renders no SVG — the profile records that as a device test, for content and for a cover
wrapper alike — so Galley uses a plain XHTML `img` pointing at the OPF cover
image. Pandoc builds its cover page from the epub3 template, which wraps the image in an inline
SVG for scaling, and `--template` is the supported way to change that.

The template is taken from the installed Pandoc rather than vendored, so nothing here can drift
away from the writer that consumes it. The patch is not trusted either: the cover in the built
book is measured, and a book whose cover is not an `img` element referencing the OPF cover image
is refused rather than published.
"""

from pathlib import Path

from galley.tools.dependencies import run_dependency

TEMPLATE_ARGUMENT = "--print-default-template=epub3"
TEMPLATE_NAME = "epub3-cover.template"
COVER_BLOCK = "$if(coverpage)$"
BLOCK_END = "$endif$"
OPENED = "<svg"
CLOSED = "</svg>"
IMAGE = "<image"
DIRECT_IMAGE = '<img src="../media/$cover-image$" alt="" />'


def cover_template(command: str, workspace: Path) -> Path | None:
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
