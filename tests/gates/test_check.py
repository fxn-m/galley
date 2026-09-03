from collections.abc import Sequence

import pytest
from scripts.check import GATES, Gate, run_gates


def test_gate_order_is_the_definition_of_done() -> None:
    assert [gate.name for gate in GATES] == [
        "formatting",
        "linting",
        "line count",
        "skill validation",
        "regex allowlist",
        "import layers",
        "Modelled Set",
        "source kinds",
        "Repair Conventions",
        "record shapes",
        "Device Profile",
        "strict typing",
        "tests",
    ]


def test_aggregate_gate_stops_and_names_a_failed_child(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gates = (
        Gate("first", ("first-command",)),
        Gate("broken", ("broken-command",)),
        Gate("unreached", ("unreached-command",)),
    )
    commands: list[Sequence[str]] = []

    def run(command: Sequence[str]) -> int:
        commands.append(command)
        return 7 if command[0] == "broken-command" else 0

    assert run_gates(gates, runner=run) == 7
    assert commands == [("first-command",), ("broken-command",)]
    assert "check: FAILED broken (exit 7)" in capsys.readouterr().err
