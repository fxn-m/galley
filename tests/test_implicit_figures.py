"""Keep Pandoc's implicit figures enabled on the Markdown route.

Disabling implicit figures can quietly remove a caption an author wrote, so this test makes that
failure loud. A footnote living in a caption otherwise leaves the book entirely, and `prepare`
then refuses at Text Preservation rather than shipping it.
"""

import json
from pathlib import Path
from typing import Any

from tests.image_fixtures import grayscale_png
from tests.markdown_fixtures import CAPTIONED_FIGURE, write_markdown
from tests.prepared_epub import PreparedEpub
from tests.public_cli import run_cli

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")


def test_an_image_alone_on_a_line_keeps_the_caption_its_author_wrote(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "figure.md", CAPTIONED_FIGURE)
    _ = grayscale_png(tmp_path / "figure.png", width=40, height=30)

    output = tmp_path / "book-0.epub"
    result = run_cli("prepare", str(source), "--output", str(output), *ARGUMENTS)
    report: Any = json.loads(result.stdout)
    book = PreparedEpub(output)
    text = book.content_text()

    assert (result.returncode, report["outcome"]) == (0, "completed")
    # The words in the brackets are printed, and the note inside them survives with them.
    assert "A diagram of the loom" in text
    assert "The loom is the whole comparison." in text
    assert report["artifact"]["text_preservation"]["tokens"]["unexpected_missing"] == []
