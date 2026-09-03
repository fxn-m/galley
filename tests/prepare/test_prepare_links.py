import json
from pathlib import Path
from typing import Any

from tests.support.markdown_fixtures import (
    MIXED_LINKS,
    NOTELIKE_WITHOUT_NOTES,
    PLAIN_BOOK,
    blocked_links,
    write_markdown,
)
from tests.support.prepared_epub import PreparedEpub
from tests.support.public_cli import prepare, run_cli

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
KINDS = (
    "cross-reference",
    "dead-link",
    "footnote-back-link",
    "footnote-reference",
    "web-link",
)


def stripping(report: Any) -> Any:
    return next(
        entry for entry in report["preparation"]["transforms"] if entry["name"] == "link-stripping"
    )


def counted(entry: Any, kind: str, field: str) -> int:
    return int(entry["kinds"][kind][field]["value"])


def test_every_content_link_is_classified_into_one_of_the_five_link_kinds(tmp_path: Path) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", MIXED_LINKS)
    journey = prepare(tmp_path, prepared_source)
    _, report = journey.output, journey.report

    entry = stripping(report)
    assert sorted(entry["kinds"]) == sorted(KINDS)
    assert sum(counted(entry, kind, "before") for kind in KINDS) == 7
    assert entry["total"]["before"]["value"] == 7
    assert counted(entry, "web-link", "before") == 1
    assert counted(entry, "dead-link", "before") == 1
    assert counted(entry, "footnote-reference", "before") == 0
    assert counted(entry, "footnote-back-link", "before") == 0
    assert counted(entry, "cross-reference", "before") == 5


def test_web_and_dead_destinations_lose_their_href_while_keeping_their_words(
    tmp_path: Path,
) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", MIXED_LINKS)
    journey = prepare(tmp_path, prepared_source)
    output, report = journey.output, journey.report

    entry = stripping(report)
    for kind in ("web-link", "dead-link"):
        assert counted(entry, kind, "removed") == counted(entry, kind, "before")
        assert counted(entry, kind, "after") == 0
    book = PreparedEpub(output)
    targets = {href for _, href, _ in book.content_anchors()}
    assert "https://example.com/outside" not in targets
    assert "chapter-two.xhtml#absent" not in targets
    text = book.content_text()
    assert "outbound" in text and "broken" in text and "inbound" in text


def test_cross_references_go_only_where_a_footnote_apparatus_is_recognised(
    tmp_path: Path,
) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", MIXED_LINKS)
    journey = prepare(tmp_path, prepared_source)
    _, recognised = journey.output, journey.report
    prepared_source = write_markdown(tmp_path / "control.md", NOTELIKE_WITHOUT_NOTES)
    journey2 = prepare(tmp_path, prepared_source)
    _, unrecognised = journey2.output, journey2.report

    with_apparatus = stripping(recognised)
    assert with_apparatus["interlock"]["apparatus_recognised"] is True
    assert with_apparatus["interlock"]["engaged"] is False
    assert counted(with_apparatus, "cross-reference", "after") == 0

    without = stripping(unrecognised)
    assert without["interlock"]["apparatus_recognised"] is False
    assert without["interlock"]["engaged"] is True
    assert without["interlock"]["notes"]["value"] == 0
    assert counted(without, "cross-reference", "removed") == 0
    assert counted(without, "cross-reference", "after") == 2
    assert "indistinguishable" in without["note"]


def test_a_zero_note_document_cannot_retain_a_note_reference_link(tmp_path: Path) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", NOTELIKE_WITHOUT_NOTES)
    journey = prepare(tmp_path, prepared_source)
    output, report = journey.output, journey.report

    entry = stripping(report)
    assert counted(entry, "footnote-reference", "before") == 0
    assert counted(entry, "footnote-back-link", "before") == 0
    assert counted(entry, "cross-reference", "before") == 2
    book = PreparedEpub(output)
    marked = [text for _, _, text in book.content_anchors()]
    assert "notelike" in marked


def test_empty_anchors_are_not_counted_as_recorded_links(tmp_path: Path) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", MIXED_LINKS)
    journey = prepare(tmp_path, prepared_source)
    _, report = journey.output, journey.report

    entry = stripping(report)
    assert entry["total"]["before"]["value"] == 7
    assert entry["recorded"]["before"]["value"] == 5
    assert entry["interlock"]["in_book_links"]["value"] == 6


def test_generated_navigation_is_not_altered_by_content_link_processing(tmp_path: Path) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", MIXED_LINKS)
    journey = prepare(tmp_path, prepared_source)
    output, _ = journey.output, journey.report

    book = PreparedEpub(output)
    anchors = book.navigation_anchors()
    assert anchors
    assert all(href for href, _ in anchors)
    assert [text for _, text in anchors] == ["Linked", "Footnotes"]


def test_the_report_gives_deterministic_before_and_after_counts_for_every_kind(
    tmp_path: Path,
) -> None:
    recorded: list[Any] = []
    for index in range(2):
        prepared_source = write_markdown(tmp_path / f"source-{index}.md", MIXED_LINKS)
        journey = prepare(tmp_path, prepared_source)
        _, report = journey.output, journey.report

        entry = stripping(report)
        recorded.append(entry["kinds"])
        for kind in KINDS:
            after = counted(entry, kind, "after")
            assert after == counted(entry, kind, "before") - counted(entry, kind, "removed")
            assert {value["basis"] for value in entry["kinds"][kind].values()} == {"measured"}

    assert recorded[0] == recorded[1]


def test_human_output_names_what_the_transform_removed_and_what_it_retained(
    tmp_path: Path,
) -> None:
    removed = write_markdown(tmp_path / "mixed-0.md", MIXED_LINKS)
    retained = write_markdown(tmp_path / "notes-0.md", NOTELIKE_WITHOUT_NOTES)
    stripped = run_cli(
        "prepare",
        str(removed),
        "--output",
        str(tmp_path / "stripped-0.epub"),
        "--profile",
        "x4-crosspoint",
    )
    interlocked = run_cli(
        "prepare",
        str(retained),
        "--output",
        str(tmp_path / "interlocked-0.epub"),
        "--profile",
        "x4-crosspoint",
    )

    assert (stripped.returncode, interlocked.returncode) == (0, 0)
    assert "Transform: link-stripping (fired)\n" in stripped.stdout
    assert (
        "Links: 7 classified; destinations removed: cross-reference 5, dead-link 1, web-link 1\n"
    ) in stripped.stdout
    assert (
        "Links: 4 classified; destinations removed: dead-link 1, web-link 1; "
        "cross-references retained, no Footnote Apparatus recognised\n"
    ) in interlocked.stdout


def test_a_document_with_no_link_says_the_transform_had_nothing_to_remove(
    tmp_path: Path,
) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", PLAIN_BOOK)
    journey = prepare(tmp_path, prepared_source)
    _, report = journey.output, journey.report

    entry = stripping(report)
    assert entry["fired"] is False
    assert entry["total"]["before"]["value"] == 0
    assert "nothing to remove" in entry["note"]
    assert report["preparation"]["canonical_document"]["transformed"] is False


def test_prepare_refuses_every_measured_navigation_boundary_but_accepts_its_limit(
    tmp_path: Path,
) -> None:
    cases = (
        ("recorded-links-per-block", blocked_links(128), blocked_links(129), 129, "recorded links"),
    )
    command_index = 0
    for case_index, (requirement_id, accepted, refused, measured, unit) in enumerate(cases):
        prefix = f"{command_index}-{case_index}"
        accepted_source = write_markdown(tmp_path / f"accepted-{prefix}.md", accepted)
        accepted_output = tmp_path / f"accepted-{prefix}.epub"
        completed = run_cli(
            "prepare", str(accepted_source), "--output", str(accepted_output), *ARGUMENTS
        )

        assert (completed.returncode, completed.stderr) == (0, "")
        assert accepted_output.is_file()

        refused_source = write_markdown(tmp_path / f"refused-{prefix}.md", refused)
        original = refused_source.read_bytes()
        refused_output = tmp_path / f"refused-{prefix}.epub"
        result = run_cli(
            "prepare", str(refused_source), "--output", str(refused_output), *ARGUMENTS
        )

        assert (result.returncode, result.stderr) == (3, "")
        report = json.loads(result.stdout)
        refusal = report["refusal"]
        assert refusal["boundary"] == "compatibility"
        assert refusal["authority"] == "prepare"
        assert refusal["stage"] == "artifact-compatibility"
        assert refusal["artifact_written"] is False
        assert refusal["fact"]["false_verdicts"] == [
            entry
            for entry in report["compatibility"]
            if entry["verdict"] == "false" and entry["authority"] == "refuse"
        ]
        verdict = refusal["fact"]["false_verdicts"][0]
        assert verdict["requirement_id"] == requirement_id
        assert verdict["measurement"]["basis"] == "measured"
        assert verdict["measurement"]["unit"] == unit
        assert verdict["measurement"]["value"] == measured
        assert verdict["measurement"]["definition"]
        assert verdict["authority"] == "refuse"
        assert not refused_output.exists()
        assert refused_source.read_bytes() == original
        assert (tmp_path / f"refused-{prefix}.galley" / "report.json").is_file()


def test_prepare_can_no_longer_breach_the_href_limit_at_all(tmp_path: Path) -> None:
    """The other refusing navigation requirement has no `prepare` case above, and that is the
    point rather than an omission. Galley bounds every identifier it hands the writer, so a
    heading that would once have produced a 97-byte navigation href now produces one inside the
    limit and the book is built. `audit` still measures a foreign artifact that breaches it, which
    is where the requirement is now exercised against real over-limit bytes."""

    over_limit = "a" * (97 - len("text/ch001.xhtml#"))
    document = f"# Target {{#{over_limit}}}\n\nA [note](#{over_limit}).\n"
    source = write_markdown(tmp_path / "bounded-0.md", document)
    output = tmp_path / "bounded-0.epub"
    result = run_cli("prepare", str(source), "--output", str(output), *ARGUMENTS)

    assert (result.returncode, result.stderr) == (0, "")
    report = json.loads(result.stdout)
    measured = report["artifact"]["links"]["maximum_recorded_href_bytes"]["value"]
    assert measured <= 96
    assert report["artifact"]["links"]["dead"] == []
