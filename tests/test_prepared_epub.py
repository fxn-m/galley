"""EPUB observations follow declared roles and links, independently of generated filenames."""

from pathlib import Path

import pytest

from tests.epub_fixtures import CHAPTER_PATH, chapter, default_entries, replace, write_epub
from tests.prepared_epub import PreparedEpub


@pytest.mark.parametrize("cover_role", ["guide", "landmark", "body"])
def test_body_cover_and_navigation_follow_package_roles(tmp_path: Path, cover_role: str) -> None:
    artifact = write_epub(
        tmp_path / "roles.epub",
        [
            ("mimetype", b"application/epub+zip"),
            (
                "META-INF/container.xml",
                b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                b'<rootfiles><rootfile full-path="Books/edition/package.opf"/>'
                b"</rootfiles></container>",
            ),
            (
                "Books/edition/package.opf",
                b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                b'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                b"<dc:title>Role Fixture</dc:title></metadata><manifest>"
                b'<item id="front" href="text/front.xhtml" media-type="application/xhtml+xml"/>'
                b'<item id="body" href="text/cover.xhtml" media-type="application/xhtml+xml"/>'
                b'<item id="nav" href="menu.xhtml" media-type="application/xhtml+xml" '
                b'properties="nav"/>'
                b'<item id="art" href="../art/picture%20one.png" media-type="image/png" '
                b'properties="cover-image"/>'
                b'</manifest><spine><itemref idref="front" linear="no"/>'
                b'<itemref idref="nav"/><itemref idref="body"/></spine>'
                + (
                    b'<guide><reference type="cover" href="text/front.xhtml#start"/></guide>'
                    if cover_role == "guide"
                    else b""
                )
                + b"</package>",
            ),
            (
                "Books/edition/menu.xhtml",
                chapter(
                    '<nav epub:type="toc"><ol><li><a href="text/cover.xhtml#body">'
                    "Body chapter</a></li></ol></nav>"
                    + (
                        '<nav epub:type="landmarks"><a epub:type="cover" href="text/front.xhtml">Cover</a></nav>'
                        if cover_role == "landmark"
                        else ""
                    )
                ),
            ),
            (
                "Books/edition/text/front.xhtml",
                chapter(
                    ('<section epub:type="cover">' if cover_role == "body" else "<section>")
                    + '<p>Cover lettering</p><img src="../../art/picture%20one.png" alt=""/></section>'
                ),
            ),
            (
                "Books/edition/text/cover.xhtml",
                chapter(
                    '<h1 id="body">Body chapter</h1> <p>The work.</p>'
                    '<img src="../../art/picture%20one.png" alt="A figure using the cover bytes"/>'
                ),
            ),
            ("Books/art/picture one.png", b"declared image bytes"),
            ("decoy/text/cover.xhtml", chapter("Wrong suffix match")),
        ],
    )

    book = PreparedEpub(artifact)

    assert book.metadata("title") == ["Role Fixture"]
    assert book.spine_documents() == ["text/front.xhtml", "menu.xhtml", "text/cover.xhtml"]
    assert book.cover_documents() == ["text/front.xhtml"]
    assert book.body_documents() == ["text/cover.xhtml"]
    assert book.content_text() == "Body chapter The work."
    assert book.navigation_anchors() == [("text/cover.xhtml#body", "Body chapter")]
    assert book.image_sources() == [
        ("text/cover.xhtml", "../../art/picture%20one.png", "A figure using the cover bytes")
    ]
    assert book.image_sources(role="cover") == [
        ("text/front.xhtml", "../../art/picture%20one.png", "")
    ]
    assert book.resource_for("text/front.xhtml", "../../art/picture%20one.png") == (
        "../art/picture%20one.png"
    )
    assert book.cover_resource() == "../art/picture%20one.png"
    assert book.media_resources() == {"../art/picture%20one.png": b"declared image bytes"}


def test_readings_are_isolated_snapshots_of_each_artifact(tmp_path: Path) -> None:
    artifact = write_epub(tmp_path / "book.epub")
    original = PreparedEpub(artifact)

    _ = write_epub(artifact, replace(default_entries(), CHAPTER_PATH, chapter("Changed body.")))
    changed = PreparedEpub(artifact)
    artifact.unlink()

    assert "A paragraph with an external link." in original.content_text()
    assert "Changed body." not in original.content_text()
    assert changed.content_text() == "Changed body."
    assert original.image_sources() == [
        ("chapter-1.xhtml", "images/figure.png", "A one-pixel figure")
    ]
    assert changed.image_sources() == []
    assert changed.cover_resource() is None
