"""Discover and inspect Device Profiles from the command line."""

import json
from typing import Annotated, cast

import typer

from galley.profile.errors import profile_error_document
from galley.profile.loading import (
    ProfileError,
    list_profiles,
    load_profile,
    profile_summary,
    render_profile,
)
from galley.reader_software import render_observed_software

profiles_app = typer.Typer(help="Discover and inspect Device Profiles.")


def register(app: typer.Typer) -> None:
    """Attach the profile commands to the Galley application."""

    app.add_typer(profiles_app, name="profiles")


@profiles_app.command("list")
def profiles_list(
    as_json: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """List available Device Profiles."""

    profiles = [profile_summary(profile) for profile in list_profiles()]
    if as_json:
        typer.echo(json.dumps(profiles, indent=2, sort_keys=True))
        return
    for profile in profiles:
        software = cast(dict[str, object], profile["observed_software"])
        typer.echo(
            f"{profile['id']}: {profile['device']} / {profile['reader']} "
            f"(profile {profile['profile_version']}, {render_observed_software(software)})"
        )


@profiles_app.command("show")
def profiles_show(
    profile_id: Annotated[str, typer.Argument(help="Device Profile identifier.")],
    as_json: Annotated[bool, typer.Option("--json", help="Emit stable JSON.")] = False,
) -> None:
    """Show one assembled Device Profile."""

    try:
        profile = load_profile(profile_id)
    except ProfileError as error:
        if as_json:
            document = profile_error_document(profile_id, str(error))
            typer.echo(json.dumps(document, indent=2, sort_keys=True))
            raise typer.Exit(2) from None
        raise typer.BadParameter(str(error), param_hint="PROFILE") from None
    if as_json:
        typer.echo(json.dumps(profile, indent=2, sort_keys=True))
        return
    typer.echo(render_profile(profile), nl=False)
