"""Repair an Article-Like Page's Canonical Document without retrieving the page a second time."""

import json
from contextlib import contextmanager
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

from tests.article_fixtures import ARTICLE
from tests.article_server import served
from tests.prepared_epub import content_text, navigation_entries
from tests.public_cli import run_cli, NO_DEFUDDLE
from tests.repair_fixtures import RepairInputs, inspected, repaired_document

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")


@contextmanager
def article_repair(tmp_path: Path) -> Generator[tuple[str, RepairInputs]]:
    """Inspect one served page, then hand back a repair that restores its heading level.

    Heading levels are something an agent can restore and the CLI cannot infer. The repair moves
    no text at all, so what the built book proves is that the repaired structure
    reached the pipeline rather than the extracted one.
    """

    with served(ARTICLE) as url:
        evidence = inspected(tmp_path / "page.galley", url)
    document = json.loads((evidence / "canonical-document.json").read_text(encoding="utf-8"))
    ast = document["pandoc"]
    for block in ast["blocks"]:
        if block["t"] == "Header":
            block["c"][0] = 1
    canonical = repaired_document(evidence, tmp_path / "repaired.json", ast)
    yield (
        url,
        RepairInputs(evidence / "report.json", canonical, evidence / "preservation-baseline.txt"),
    )


def test_a_repaired_article_is_prepared_without_extracting_the_page_again(
    tmp_path: Path,
) -> None:
    with article_repair(tmp_path) as (url, repair):
        # The server is down and the extractor is unreachable. A repaired preparation needs
        # neither: the document it packages already exists, which is the whole point of the route.
        output = tmp_path / "book-0.epub"
        result = run_cli(
            "prepare",
            url,
            "--output",
            str(output),
            *ARGUMENTS,
            *repair.options,
            environment=NO_DEFUDDLE,
        )
        report: Any = json.loads(result.stdout)

        assert (result.returncode, report["outcome"]) == (0, "completed")
        assert "defuddle" not in report["galley"]["dependencies"]
        # The extracted document lists only the essay title at this depth; the section
        # heading appears because the repaired structure is what was packaged.
        assert report["source"]["repair"]["changed"] is True
        assert navigation_entries(output) == ["A Small Essay", "A section inside it"]
        assert "Enginewise" in content_text(output)
        assert report["artifact"]["text_preservation"]["tokens"]["unexpected_missing"] == []


def test_facts_the_repaired_run_did_not_establish_are_reported_not_measured(
    tmp_path: Path,
) -> None:
    with article_repair(tmp_path) as (url, repair):
        inspection = json.loads(repair.report.read_text(encoding="utf-8"))

        result = run_cli(
            "prepare",
            url,
            "--output",
            str(tmp_path / "book-0.epub"),
            *ARGUMENTS,
            *repair.options,
            environment=NO_DEFUDDLE,
        )
        report: Any = json.loads(result.stdout)

        assert result.returncode == 0
        assert _bases(report["extraction"]) == {"reported"}
        assert _bases(report["source"]) == set()
        assert (
            report["extraction"]["words"]["value"] == (inspection["extraction"]["words"]["value"])
        )
        assert report["source"]["url"] == url
        assert report["source"]["repair"]["source"] == {
            "kind": "article-url",
            "path": None,
            "sha256": None,
            "url": url,
        }
        # The document this run did read is measured, so inheritance never spreads.
        assert _bases(report["canonical_document"]["reading"]) == {"measured"}


def _bases(facts: object) -> set[str]:
    """Collect every basis a fact object states, however deeply it is nested."""

    if isinstance(facts, dict):
        node = cast(dict[str, object], facts)
        stated = {str(node["basis"])} if "basis" in node and "value" in node else set[str]()
        return stated.union(*(_bases(value) for value in node.values()), set[str]())
    if isinstance(facts, list):
        return set[str]().union(*(_bases(item) for item in cast(list[object], facts)), set[str]())
    return set[str]()
