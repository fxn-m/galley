"""Project and render generic Observed Reader Software identity."""

from typing import cast


def observed_software(profile: dict[str, object]) -> dict[str, object]:
    """Select one Device Profile's reader-software observation."""

    software = cast(dict[str, object], profile["software"])
    return {
        "kind": software["kind"],
        "version": software["version"],
        "operating_system": software["operating_system"],
        "observed_at": software["observed_at"],
    }


def render_observed_software(software: dict[str, object]) -> str:
    """Render firmware or application identity without conflating the two."""

    kind = str(software["kind"])
    version = software["version"]
    rendered = f"{kind} {version}" if version is not None else f"{kind} not yet observed"
    operating_system = software["operating_system"]
    if isinstance(operating_system, dict):
        system = cast(dict[str, object], operating_system)
        name = system["name"]
        system_version = system["version"]
        rendered += f" on {name} {system_version or 'not yet observed'}"
    return rendered
