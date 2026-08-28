import shutil
from pathlib import Path

import pytest

from galley.profile import loading
from galley.profile.loading import list_profiles, profile_summary, render_profile
from galley.profile.reading import ProfileError
from galley.profile.validation import assemble_profile

PROFILE = Path("profiles/x4-crosspoint")


def copy_profile(tmp_path: Path) -> Path:
    target = tmp_path / "x4-crosspoint"
    _ = shutil.copytree(PROFILE, target)
    return target


def replace(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    assert old in source
    _ = path.write_text(source.replace(old, new, 1), encoding="utf-8")


def test_committed_profile_is_valid() -> None:
    _ = assemble_profile(PROFILE / "profile.yaml")


def test_a_profile_version_can_begin_independently_of_the_schema_version(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(profile / "profile.yaml", "profile_version: 0.4.0", "profile_version: 1.0.0")

    assembled = assemble_profile(profile / "profile.yaml")

    assert assembled["schema"] == "galley/device-profile/2"
    assert assembled["profile_version"] == "1.0.0"


def test_an_application_revision_carries_its_operating_system_without_becoming_firmware(
    tmp_path: Path,
) -> None:
    profile = copy_profile(tmp_path)
    replace(
        profile / "profile.yaml",
        '  kind: firmware\n  version: "1.4.1"\n  observed_at: "2026-08-16"\n'
        "  operating_system: null",
        '  kind: application\n  version: "7.18"\n  observed_at: "2026-08-27"\n'
        '  operating_system:\n    name: iOS\n    version: "18.6"',
    )

    assembled = assemble_profile(profile / "profile.yaml")

    assert profile_summary(assembled)["observed_software"] == {
        "kind": "application",
        "observed_at": "2026-08-27",
        "operating_system": {"name": "iOS", "version": "18.6"},
        "version": "7.18",
    }
    rendered = render_profile(assembled)
    assert "observed application 7.18 on iOS 18.6" in rendered
    assert "firmware 7.18" not in rendered


def test_profile_discovery_rejects_duplicate_public_ids_deterministically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = shutil.copytree(PROFILE, tmp_path / "first")
    _ = shutil.copytree(PROFILE, tmp_path / "second")
    monkeypatch.setattr(loading, "SOURCE_PROFILES", tmp_path)

    with pytest.raises(ProfileError, match="^duplicate Device Profile id: x4-crosspoint$"):
        _ = list_profiles()


def test_profile_rejects_a_malformed_manifest(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    _ = (profile / "profile.yaml").write_text("parts: [\n", encoding="utf-8")

    with pytest.raises(ProfileError, match="malformed YAML"):
        _ = assemble_profile(profile / "profile.yaml")


def test_profile_rejects_a_missing_fragment(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(
        profile / "profile.yaml",
        "requirements/recorded-links-per-block.yaml",
        "requirements/missing.yaml",
    )

    with pytest.raises(ProfileError, match="missing or unsafe fragment path"):
        _ = assemble_profile(profile / "profile.yaml")


def test_profile_rejects_unsafe_fragment_paths(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(profile / "profile.yaml", "requirements/recorded", "../recorded")

    with pytest.raises(ProfileError, match="unsafe fragment path"):
        _ = assemble_profile(profile / "profile.yaml")


def test_profile_rejects_duplicate_identifiers(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(profile / "requirements/png-decoding.yaml", "id: png-decoding", "id: jpeg-decoding")

    with pytest.raises(ProfileError, match="duplicate id"):
        _ = assemble_profile(profile / "profile.yaml")


def test_profile_rejects_malformed_evidence_claims(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(profile / "requirements/anchors-per-chapter.yaml", '    source_tag: "1.4.1"\n', "")

    with pytest.raises(ProfileError, match="source_tag"):
        _ = assemble_profile(profile / "profile.yaml")


def test_profile_rejects_invalid_refusal_authority(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(profile / "requirements/png-decoding.yaml", "authority: report", "authority: refuse")

    with pytest.raises(ProfileError, match="cannot carry refusal authority"):
        _ = assemble_profile(profile / "profile.yaml")


def test_profile_rejects_invalid_activation_references(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(
        profile / "activation.yaml",
        "justified_by: one-file-per-note-resolves",
        "justified_by: missing-behaviour",
    )

    with pytest.raises(ProfileError, match="missing-behaviour"):
        _ = assemble_profile(profile / "profile.yaml")


def test_profile_rejects_raster_types_that_disagree_with_its_colour_model(
    tmp_path: Path,
) -> None:
    profile = copy_profile(tmp_path)
    replace(profile / "activation.yaml", "colour_model: grayscale", "colour_model: rgb")

    with pytest.raises(ProfileError, match="rgb raster colour types must be 2 and 6"):
        _ = assemble_profile(profile / "profile.yaml")


def test_profile_rejects_an_incomplete_cover_direction(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(
        profile / "activation.yaml",
        "      thumbnail_intent: legible-at-device-cover-thumbnail\n",
        "",
    )

    with pytest.raises(ProfileError, match="cover_artwork.value must name exactly"):
        _ = assemble_profile(profile / "profile.yaml")


def test_profile_rejects_a_cover_canvas_outside_its_raster_fit(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(profile / "activation.yaml", "        width_px: 480", "        width_px: 481")

    with pytest.raises(ProfileError, match="cover canvas exceeds image fit max_width_px"):
        _ = assemble_profile(profile / "profile.yaml")


def test_profile_rejects_unlisted_fragments(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    _ = (profile / "requirements/extra.yaml").write_text("id: extra\n", encoding="utf-8")

    with pytest.raises(ProfileError, match="unlisted fragment"):
        _ = assemble_profile(profile / "profile.yaml")


def test_a_support_matrix_naming_an_unmeasurable_field_is_rejected(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(
        profile / "requirements/png-decoding.yaml",
        "{sample_depth: 8, colour_types: [0, 2, 3, 4, 6]}",
        "{sample_depth: 8, colour_type: [0, 2, 3, 4, 6]}",
    )

    with pytest.raises(ProfileError, match="unknown field colour_type"):
        _ = assemble_profile(profile / "profile.yaml")


def test_a_support_matrix_naming_an_unknown_section_is_rejected(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(
        profile / "requirements/png-decoding.yaml", "  unlisted: unknown", "  untested: unknown"
    )

    with pytest.raises(ProfileError, match="unknown field untested"):
        _ = assemble_profile(profile / "profile.yaml")


def test_an_unbindable_subject_declaration_is_rejected(tmp_path: Path) -> None:
    profile = copy_profile(tmp_path)
    replace(
        profile / "requirements/png-decoding.yaml",
        "  measured_media_types: [image/png]",
        "  declared_media_types: [image/png]",
    )

    with pytest.raises(ProfileError, match="measured_media_types"):
        _ = assemble_profile(profile / "profile.yaml")
