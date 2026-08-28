import json
import shutil
import sys
from pathlib import Path
from typing import Any

from tests.image_fixtures import grayscale_png
from tests.epub_fixtures import write_epub
from tests.markdown_fixtures import write_markdown
from tests.public_cli import NO_EPUBCHECK, public_cli_commands, run_command, run_public_cli

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
LOST_SENTENCE = "Caf\u0065\u0301 café `can't` can’t Echo Echo."
LOST_MARKUP = "<p>Caf\u0065\u0301 café <code>can't</code> can’t Echo Echo.</p>"
PRESERVED_TEXT = """# Opening

Caf\u0065\u0301 can't can’t Echo Echo before note.[^n]

![River map](figure.png)

Final block.

[^n]: Note wording moves into its own spine document.
"""


def preservation(report: Any) -> Any:
    return report["artifact"]["text_preservation"]


def sentence_eating_pandoc(directory: Path) -> Path:
    """Wrap the real Pandoc writer, then remove one known sentence from its EPUB output."""

    real = shutil.which("pandoc")
    assert real is not None
    wrapper = directory / "sentence-eating-pandoc"
    program = f"""#!{sys.executable}
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

completed = subprocess.run([{real!r}, *sys.argv[1:]], check=False)
arguments = sys.argv[1:]
if completed.returncode == 0 and "--to" in arguments and "epub3" in arguments:
    output = Path(arguments[arguments.index("--output") + 1])
    replacement = output.with_suffix(".eaten.epub")
    with ZipFile(output) as source, ZipFile(replacement, "w") as changed:
        for entry in source.infolist():
            payload = source.read(entry.filename)
            if entry.filename.endswith("ch001.xhtml"):
                payload = payload.replace({LOST_MARKUP!r}.encode("utf-8"), b"")
            elif entry.filename.endswith("nav.xhtml"):
                payload = payload.replace(
                    b"</body>", {LOST_MARKUP!r}.encode("utf-8") + b"</body>"
                )
            elif entry.filename.endswith("content.opf"):
                payload = payload.replace(
                    b"</spine>", b'<itemref idref="nav" linear="yes" />\\n</spine>'
                )
            changed.writestr(entry, payload)
    os.replace(replacement, output)
raise SystemExit(completed.returncode)
"""
    _ = wrapper.write_text(program, encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


def test_prepare_measures_normalised_visible_text_after_restructuring(tmp_path: Path) -> None:
    _ = grayscale_png(tmp_path / "figure.png")

    for index, command in enumerate(public_cli_commands("prepare")):
        source = write_markdown(tmp_path / f"source-{index}.md", PRESERVED_TEXT)
        output = tmp_path / f"book-{index}.epub"

        result = run_command(command, str(source), "--output", str(output), *ARGUMENTS)

        assert (result.returncode, result.stderr) == (0, "")
        facts = preservation(json.loads(result.stdout))
        assert facts["claimed"] is True
        assert facts["basis"] == "measured"
        assert facts["normalization"] == "NFC"
        assert facts["tokens"]["baseline"]["value"] == 20
        assert facts["tokens"]["artifact"]["value"] >= 20
        assert facts["tokens"]["expected_missing"] == []
        assert facts["tokens"]["unexpected_missing"] == []
        assert facts["characters"]["authoritative"] is False
        assert facts["characters"]["identical"] is False
        assert output.is_file()


def test_unexpected_missing_tokens_refuse_but_declared_losses_are_allowed(
    tmp_path: Path,
) -> None:
    wrapper = sentence_eating_pandoc(tmp_path)
    text = f"# Kept\n\nOpening words.\n\n{LOST_SENTENCE}\n\nClosing words.\n"
    expected = {"Café": 1, "café": 1, "can't": 1, "can’t": 1, "Echo": 2}
    declarations = tmp_path / "expected.json"
    _ = declarations.write_text(json.dumps(expected), encoding="utf-8")

    for index, command in enumerate(public_cli_commands("prepare")):
        source = write_markdown(tmp_path / f"eaten-{index}.md", text)
        refused_output = tmp_path / f"refused-{index}.epub"
        environment = {"GALLEY_PANDOC": str(wrapper)}

        refused = run_command(
            command,
            str(source),
            "--output",
            str(refused_output),
            *ARGUMENTS,
            environment=environment,
        )

        assert (refused.returncode, refused.stderr) == (3, "")
        report = json.loads(refused.stdout)
        assert report["refusal"]["boundary"] == "text-preservation"
        assert report["refusal"]["stage"] == "text-preservation"
        assert report["refusal"]["artifact_written"] is False
        assert preservation(report)["tokens"]["unexpected_missing"] == [
            {"count": {"basis": "measured", "unit": "tokens", "value": count}, "token": token}
            for token, count in sorted(expected.items())
        ]
        assert not refused_output.exists()
        assert (tmp_path / f"refused-{index}.galley" / "report.json").is_file()

        allowed_output = tmp_path / f"allowed-{index}.epub"
        allowed = run_command(
            command,
            str(source),
            "--output",
            str(allowed_output),
            *ARGUMENTS,
            "--expected-missing-tokens",
            str(declarations),
            environment=environment,
        )

        assert (allowed.returncode, allowed.stderr) == (0, "")
        allowed_facts = preservation(json.loads(allowed.stdout))
        assert {
            entry["token"]: entry["count"]["value"]
            for entry in allowed_facts["tokens"]["expected_missing"]
        } == expected
        assert allowed_facts["tokens"]["unexpected_missing"] == []
        assert allowed_output.is_file()


def test_audit_without_a_baseline_makes_no_text_preservation_claim(tmp_path: Path) -> None:
    book = write_epub(tmp_path / "foreign.epub")

    structured = run_public_cli("audit", str(book), *ARGUMENTS, environment=NO_EPUBCHECK)
    rendered = run_public_cli(
        "audit", str(book), "--profile", "x4-crosspoint", environment=NO_EPUBCHECK
    )

    for result in structured:
        assert result.returncode == 0
        assert preservation(json.loads(result.stdout)) == {
            "claimed": False,
            "detail": "Preservation Baseline unavailable",
            "reason": "preservation-baseline-unavailable",
        }
    for result in rendered:
        assert result.returncode == 0
        assert (
            "Text Preservation: not claimed (Preservation Baseline unavailable)\n" in result.stdout
        )


def test_expected_loss_declarations_are_immutable_workflow_inputs(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "source.md", "# Kept\n\nEvery token survives.\n")

    for command_index, command in enumerate(public_cli_commands("prepare")):
        for collision in ("artifact", "report", "evidence"):
            prefix = f"{command_index}-{collision}"
            output = tmp_path / f"book-{prefix}.epub"
            arguments: list[str] = []
            if collision == "artifact":
                declarations = tmp_path / f"expected-{prefix}.json"
                output = declarations
            elif collision == "report":
                declarations = tmp_path / f"expected-{prefix}.json"
                arguments = ["--report-out", str(declarations)]
            else:
                evidence = tmp_path / f"evidence-{prefix}"
                evidence.mkdir()
                declarations = evidence / "report.json"
                arguments = ["--evidence-dir", str(evidence)]
            original = b"{}\n"
            _ = declarations.write_bytes(original)

            result = run_command(
                command,
                str(source),
                "--output",
                str(output),
                *ARGUMENTS,
                "--expected-missing-tokens",
                str(declarations),
                "--overwrite",
                *arguments,
            )

            assert (result.returncode, result.stderr) == (3, "")
            assert json.loads(result.stdout)["refusal"]["boundary"] == "output-is-input"
            assert declarations.read_bytes() == original
