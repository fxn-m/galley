# Authoring profile-directed Cover Artwork

Cover Artwork is a work-specific visual identity its cover author creates after reading the work. A
generic title card made without understanding the material is unfinished work. The SVG is the
creative source of truth; Galley deterministically rasterises it for the selected Device Profile.
Do not treat a packaged cover as recovered source imagery or as evidence that a later conversion
service preserved it.

During Assisted Preparation, the cover author is normally a focused cover subagent that owns the
whole creative task. When delegation is unavailable, the main agent becomes the cover author and
uses this same guide, including its visual judgment rather than only its mechanical checks.

## Read the direction, then compose

Run `galley profiles show PROFILE --json` and read
`activation.cover_artwork.value`. It supplies the exact canvas, colour model, contrast and density
guidance, type and shape scale, thumbnail intent, viewing-preview policy, and permitted font family.
Do not copy those values into reusable prose or select them from the profile id.

Read beyond the title and description. Find the work's central tension, one or two concrete visual
motifs, and its emotional register, then commit to a strong editorial concept. When the user gives
no art direction, exercise creative judgement and make that concept yourself; a first draft does
not need a separate theme-selection conversation. Treat the profile as a set of productive
constraints rather than a house style or reusable layout.

If the same work needs covers for two profiles, make two compositional decisions from the two
directions. Reusing a concept is fine; merely recolouring or resizing one universal layout is not
the profile-directed work this seam exists for.

## Author one self-contained SVG

- Set `width`, `height`, and `viewBox` to the direction's exact canvas.
- Use the direction's colour model and viewing constraints while composing, not as a conversion
  claim. A grayscale profile still receives an 8-bit grayscale PNG; a colour profile receives RGB.
- Make the title legible at the named thumbnail intent. Follow the profile's type/shape scale,
  contrast and density guidance rather than adding detail because the canvas is large.
- Keep the SVG self-contained: paths, shapes, fills and text only; no remote images, scripts,
  platform resources or installed-font assumptions.
- For title or author text, use the exact `font_family` from the direction. Galley bundles that
  OFL-licensed face and gives resvg no system fonts. If the title needs a glyph it does not carry,
  convert that text to SVG paths and retain the path source; do not name another font and accept a
  fallback. Never invent an absent author.
- Escape title and author text as XML. Keep the authored `.svg` beside the work or its retained
  evidence so the packaged PNG never becomes the editable source.

Attach the SVG as Pandoc's `cover-image` metadata. For Markdown, use a path relative to the source:

```yaml
---
title: The Work
author: The Author
cover-image: artwork/kindle-cover.svg
---
```

For an Article-Like Page already travelling through Repair Inputs, keep the authored SVG file and
set the Canonical Document's `cover-image` `MetaString` to a base64 `data:image/svg+xml` locator of
those exact bytes. A fetched page must not gain access to an arbitrary local path. This metadata
change consumes no reader-visible text; resubmit the unchanged Report, Preservation Baseline and
the edited Canonical Document through the ordinary repair-input interface.

## Prepare and verify the evidence

Use the ordinary explicit-output interface and keep evidence outside any later handoff folder:

```text
galley prepare SOURCE \
  --profile PROFILE \
  --output BOOK.epub \
  --evidence-dir BOOK.galley \
  --json
```

In `preparation.images.records`, find the entry with `cover: true` and verify all of these agree:

- source media type is SVG; `transform` is `normalised`;
- packaged and artifact media type is PNG at the profile's exact canvas, 8-bit depth and selected
  colour type;
- `packaged.renderer` names pinned resvg, `system_fonts: false`, an empty `messages` list, and the
  bundled font's family, style, version, SHA-256, licence and matching digest;
- `artifact.cover` and `artifact.referenced` are true;
- packaged and artifact SHA-256 values match;
- the authored SVG is absent from packaged media;
- the prepared preview has the exact canvas, and any viewing preview follows the profile's stated
  policy (for example, the X4 preview has at most four levels).

Renderer messages are evidence, not harmless stderr. A font warning means the requested text did
not use the deterministic face: revise it to the profile font or paths and prepare again. A missing
or malformed requested cover refuses at `image-processing-failure`; fix the SVG or its locator and
start a fresh preparation. Never remove `cover-image` merely to make the build pass.
