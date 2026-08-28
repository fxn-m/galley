"""Prove a repaired Semantic Social Embed through the installed public preparation boundary."""

from pathlib import Path

from tests.image_fixtures import grayscale_png
from tests.prepared_epub import content_anchors, content_text, element_texts, image_sources
from tests.public_cli import public_cli_commands, run_command

POST = "https://x.com/boxcardavid/status/1059347504154595329"
BODY_LINK = "https://youtu.be/NFvMC3l3fGY"
MENTION = "https://x.com/starsandrobots"
REPAIRED = """---
title: A Semantic Social Embed
---

# A Semantic Social Embed

> **Post by David Hansen (@boxcardavid)**
>
> [@starsandrobots](https://x.com/starsandrobots) found a renaissance in motor drivers. See this
> [3D-printed brushless motor](https://youtu.be/NFvMC3l3fGY).
>
> ![A 3D-printed brushless motor](motor.png)
>
> 7:31 AM · Nov 5, 2018
>
> [View original post](https://x.com/boxcardavid/status/1059347504154595329)
"""


def test_a_repaired_social_embed_survives_as_native_reflowable_epub_xhtml(
    tmp_path: Path,
) -> None:
    """Identity, meaning and routes survive; wrapper and platform chrome do not."""

    source = tmp_path / "social.md"
    _ = source.write_text(REPAIRED, encoding="utf-8")
    _ = grayscale_png(tmp_path / "motor.png")

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        artifact = tmp_path / f"social-{index}.epub"
        result = run_command(
            command,
            "--profile",
            "kindle-ios-personal-documents",
            "--output",
            str(artifact),
            "--json",
        )

        assert result.returncode == 0, result.stderr
        embeds = element_texts(artifact, "blockquote")
        assert len(embeds) == 1
        assert "Post by David Hansen (@boxcardavid)" in embeds[0]
        assert "found a renaissance in motor drivers" in embeds[0]
        assert "7:31 AM · Nov 5, 2018" in embeds[0]

        anchors = {(href, text) for _, href, text in content_anchors(artifact)}
        assert anchors == {
            (MENTION, "@starsandrobots"),
            (BODY_LINK, "3D-printed brushless motor"),
            (POST, "View original post"),
        }
        assert [(alt, src) for _, src, alt in image_sources(artifact)] == [
            ("A 3D-printed brushless motor", "../media/file0.png")
        ]

        reading = content_text(artifact)
        for chrome in (
            "X avatar for",
            "Replies",
            "Reposts",
            "Likes",
            "Views",
            "🇺🇸",
            "🇳🇿",
            "[",
            "](",
        ):
            assert chrome not in reading
