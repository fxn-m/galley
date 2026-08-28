"""What language a prepared artifact declares, and where that came from.

Pandoc fills `dc:language` from the packaging machine's locale wherever nothing states one. That
made a single source build a different book on every machine, and on a machine with no locale
configured it built an **invalid** one — `Language tag "C"`, which EPUBCheck rejects as OPF-092.
Galley states the language explicitly instead, so the writer's fallback never runs.
"""

import json
import zipfile
from pathlib import Path
from typing import Any

from galley.document.canonical import UNDETERMINED

from tests.article_fixtures import ARTICLE, filler
from tests.article_server import served
from tests.markdown_fixtures import write_markdown
from tests.public_cli import public_cli_commands, run_command

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
# A locale that is not a language tag, which is what a bare CI runner has.
BARE = {"LANG": "C", "LC_ALL": "C"}
CONFIGURED = {"LANG": "de_DE.UTF-8", "LC_ALL": "de_DE.UTF-8"}
BODY = "Prose that runs long enough to read as a document rather than a fragment of one.\n"


def prepared(tmp_path: Path, index: int, command: list[str], *extra: str, **kwargs: Any) -> Any:
    """`public_cli_commands` already carries the source where one was handed to it."""

    output = tmp_path / f"book-{index}.epub"
    result = run_command(command, *extra, "--output", str(output), *ARGUMENTS, **kwargs)
    assert (result.returncode, result.stderr) == (0, "")
    return output, json.loads(result.stdout)


def declared(artifact: Path) -> str:
    with zipfile.ZipFile(artifact) as archive:
        opf = archive.read("EPUB/content.opf").decode("utf-8")
    opening = opf.index("<dc:language>") + len("<dc:language>")
    return opf[opening : opf.index("</dc:language>", opening)]


def language(report: Any) -> Any:
    return next(
        entry
        for entry in report["preparation"]["transforms"]
        if entry["name"] == "document-language"
    )


def document(title: str, *, stated: str | None = None) -> str:
    lines = [f'title: "{title}"'] + ([f'language: "{stated}"'] if stated else [])
    return "---\n" + "\n".join(lines) + f"\n---\n\n# {title}\n\n{BODY}"


def test_the_packaging_locale_never_reaches_the_artifact(tmp_path: Path) -> None:
    """The same source, built on a bare machine and a configured one, is the same book.

    `LANG=C` is the case that mattered: Pandoc wrote `Language tag "C"` and EPUBCheck rejected the
    book outright, so this is a conformance fix before it is a determinism one.
    """

    source = write_markdown(tmp_path / "plain.md", document("A Plain Book"))

    for index, command in enumerate(public_cli_commands("prepare")):
        bare, one = prepared(tmp_path, index, command, str(source), environment=BARE)
        configured, two = prepared(
            tmp_path, index + 100, command, str(source), environment=CONFIGURED
        )

        assert declared(bare) == declared(configured) == UNDETERMINED
        assert bare.read_bytes() == configured.read_bytes()
        assert one["artifact"]["sha256"] == two["artifact"]["sha256"]


def test_a_document_stating_its_own_language_keeps_it(tmp_path: Path) -> None:
    """Both conventions are read: `lang` is Pandoc's key and `language` is what an extractor
    writes into the frontmatter it produces. Observed Markdown uses both."""

    for index, command in enumerate(public_cli_commands("prepare")):
        for offset, key in enumerate(("lang", "language")):
            body = f"---\ntitle: A Stated Book\n{key}: de-DE\n---\n\n# A Stated Book\n\n{BODY}"
            source = write_markdown(tmp_path / f"stated-{index}-{offset}.md", body)
            artifact, report = prepared(
                tmp_path, index * 10 + offset, command, str(source), environment=BARE
            )

            assert declared(artifact) == "de-DE"
            assert language(report)["language_source"] == "metadata"


def test_an_extracted_page_keeps_the_language_the_page_stated(tmp_path: Path) -> None:
    """On the article route the AST is a parse of content rather than of a page, so it carries no
    metadata of its own — the extractor's reading is the only one there is."""

    page = ARTICLE.replace("<html>", '<html lang="fr">')
    with served(page) as url:
        for index, command in enumerate(public_cli_commands("prepare", url)):
            artifact, report = prepared(tmp_path, index, command, environment=BARE)

            assert declared(artifact) == "fr"
            assert language(report)["language_source"] == "extraction"


def test_a_document_stating_nothing_declares_undetermined_and_says_so(tmp_path: Path) -> None:
    """`und` is BCP 47's tag for exactly that. Galley has not read the words, and `en` would be a
    claim about a document rather than a fact from it."""

    source = write_markdown(tmp_path / "silent.md", document("A Silent Book"))

    for index, command in enumerate(public_cli_commands("prepare")):
        artifact, report = prepared(tmp_path, index, command, str(source), environment=BARE)

        assert declared(artifact) == UNDETERMINED
        entry = language(report)
        assert (entry["fired"], entry["language_source"]) == (True, "default")
        assert "undetermined" in entry["note"]


def test_a_rejected_language_never_reaches_the_writer(tmp_path: Path) -> None:
    """Deciding not to use a stated value is not the same as the writer never seeing it.

    `dc:language` comes from Pandoc's `language` key and its translation strings from `lang`, so
    overriding only the first left a source's own `lang` in play: a document saying
    `lang: "not a tag!"` had the writer report loading translations for `not`, in the same Report
    that recorded the value as unusable. Both keys are stated now, and `und` asks for no strings
    at all rather than for a language that has none.
    """

    for index, command in enumerate(public_cli_commands("prepare")):
        for offset, key in enumerate(("lang", "language")):
            body = f'---\ntitle: An Odd Book\n{key}: "not a tag!"\n---\n\n# An Odd Book\n\n{BODY}'
            source = write_markdown(tmp_path / f"odd-{index}-{offset}.md", body)
            artifact, report = prepared(
                tmp_path, index * 10 + offset, command, str(source), environment=BARE
            )

            assert declared(artifact) == UNDETERMINED
            assert language(report)["language_source"] == "unusable"
            assert report["preparation"]["packaging"]["messages"] == []


def test_the_language_is_stated_even_where_the_page_states_none(tmp_path: Path) -> None:
    """A page with no `lang` is the article-route half of the default."""

    with served(ARTICLE + f"<!-- {filler(0)} -->") as url:
        for index, command in enumerate(public_cli_commands("prepare", url)):
            artifact, report = prepared(tmp_path, index, command, environment=BARE)

            assert declared(artifact) == UNDETERMINED
            assert language(report)["language_source"] == "default"
