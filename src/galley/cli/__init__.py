"""Galley's command-line application.

The application object and its top-level options live here; each group of commands registers
itself from its own module rather than reaching back for the application, so the wiring stays
one-directional. Command modules are only argument parsing and output — every decision a
command makes belongs to the workflow it calls.
"""

from typing import Annotated

import typer

from galley import __version__
from galley.cli.delivery import register as register_delivery
from galley.cli.profiles import register as register_profiles
from galley.cli.skills import register as register_skills
from galley.cli.sources import register as register_sources
from galley.cli.workspace import register as register_workspace
from galley.tools.dependencies import invocation

app = typer.Typer(
    help="Prepare content for constrained reading environments.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Print the installed Galley version and exit."""

    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def root(
    context: typer.Context,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback,
            help="Show the Galley version.",
        ),
    ] = False,
) -> None:
    """Own dependency identity for this command and release it when its context closes."""

    context.with_resource(invocation())


def main() -> None:
    """Run the Galley CLI."""

    app(prog_name="galley")


register_profiles(app)
register_sources(app)
register_workspace(app)
register_delivery(app)
register_skills(app)
