"""Validate the Observed Reader Software identity one Device Profile states."""

from pathlib import Path

from galley.profile.reading import ProfileError, mapping, require_keys, require_string


def validate_software(value: object, path: Path) -> None:
    """Require firmware alone or an application paired with its operating system."""

    software = mapping(value, f"{path}: software")
    require_keys(
        software,
        {"kind", "version", "observed_at", "operating_system", "queued_changes"},
        path,
    )
    kind = require_string(software.get("kind"), f"{path}: software.kind")
    if kind not in {"application", "firmware"}:
        raise ProfileError(f"{path}: invalid software kind {kind}")
    version = _nullable_string(software.get("version"), f"{path}: software.version")
    observed_at = _nullable_string(software.get("observed_at"), f"{path}: software.observed_at")
    if (version is None) != (observed_at is None):
        raise ProfileError(f"{path}: software version and observed_at must be known together")

    system = software.get("operating_system")
    if kind == "firmware":
        if system is not None:
            raise ProfileError(f"{path}: firmware must not name an operating system")
        return
    operating_system = mapping(system, f"{path}: software.operating_system")
    require_keys(operating_system, {"name", "version"}, path)
    require_string(operating_system.get("name"), f"{path}: software.operating_system.name")
    system_version = _nullable_string(
        operating_system.get("version"), f"{path}: software.operating_system.version"
    )
    if (version is None) != (system_version is None):
        raise ProfileError(
            f"{path}: application and operating-system versions must be known together"
        )


def _nullable_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return require_string(value, label)
