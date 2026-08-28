# Authoring profile-directed Cover Artwork

Cover Artwork is a work-specific visual identity its cover author creates after reading the work. A
generic title card made without understanding the material is unfinished work. The SVG is the
creative source of truth; Galley deterministically rasterises it for the selected Device Profile.
Do not treat a packaged cover as recovered source imagery or as evidence that a later conversion
service preserved it.

During Assisted Preparation, the cover author is normally a focused cover subagent that owns the
whole creative task. When delegation is unavailable, the main agent becomes the cover author and
uses this same guide, including its visual judgment rather than only its mechanical checks.

## Read the direction

Run `galley profiles show PROFILE --json` and read
`activation.cover_artwork.value`. It supplies the exact canvas, colour model, contrast and density
guidance, type and shape scale, visual hierarchy, typography role, thumbnail intent,
viewing-preview policy, and permitted font family. Do not copy those values into reusable prose or
select them from the profile id.

Treat the profile as productive constraints rather than a house style or reusable layout. If the
same work needs covers for two profiles, make two compositional decisions from the two directions.
Reusing a concept is fine; merely recolouring or resizing one universal layout is not the
profile-directed work this seam exists for.

## Understand the work

Read beyond the title and description, then search the web for visual evidence from the work,
author or relevant brand. Open the sources themselves. Keep a short trail of the URLs consulted and
the concrete cue taken from each.

Decide whether the cover should extend an established visual identity or create an original one. A
coherently designed source is strong direction: understand its palette, typography, grid, spacing
and image treatment, then make a new composition that belongs to that system. Otherwise use prior
art and the work's tension, mood and motifs to find an original direction. Research informs this
decision; it is not an ingredient list. Do not imitate one existing composition, embed reference
images, or compare against recent Galley covers.

## State one governing idea

Write one sentence that says what the cover is. It may be an image, a pattern, a typographic
composition or another work-specific form. Choose one dominant form and make every other element
serve it. Prefer an abstract fragment or shape system when a literal person, animal, machine or
multi-object scene would create more anatomical and spatial relationships than the SVG can carry
convincingly.

Use the exact title and known author; never invent an author, synopsis, quotation, tagline, badge or
decorative microcopy. A source-led typographic cover may make the title the artwork, but that does
not justify extra text.

## Establish composition before detail

Before drawing detailed artwork, make a rough block composition for the exact canvas. Decide the
dominant form, primary alignment, title area and negative space. Render those simple regions at the
profile's thumbnail size. Cropping and overlap must already look intentional; if the hierarchy or
balance needs ornament to become clear, revise the grid instead.

Only then develop the SVG. Carry through the few research cues that strengthen the governing idea,
not every cue you found. Keep all secondary elements subordinate. A second profile gets its own
block composition rather than a resized or recoloured layout.

## Author one self-contained SVG

- Set `width`, `height`, and `viewBox` to the direction's exact canvas.
- Use the direction's colour model and viewing constraints while composing, not as a conversion
  claim. A grayscale profile still receives an 8-bit grayscale PNG; a colour profile receives RGB.
- Make the whole cover recognisable and the title legible at the named thumbnail intent. Follow the
  profile's hierarchy, typography role, type/shape scale, contrast and density guidance rather than
  adding detail because the canvas is large.
- Keep the SVG self-contained: paths, shapes, fills and text only; no remote images, scripts,
  platform resources or installed-font assumptions.
- For title or author `<text>`, use the exact `font_family` from the direction. Galley bundles that
  OFL-licensed face and gives resvg no system fonts. When work-specific lettering is integral to
  the concept, it may instead be original lettering as SVG paths or paths derived from a face whose
  licence permits that use; retain the lettering source and licence evidence. Do not turn an
  unlicensed or platform font into paths or name another font and accept a fallback.
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

## Render and judge the whole

Render working previews before final preparation and inspect the whole cover, not a cropped detail,
at full size and at a small library thumbnail. For a quantised profile, inspect the stated viewing
preview too. Do not approve an SVG you have only read as markup.

Judge the whole composition: does the governing idea register, does one hierarchy control the
canvas, and do the alignments, cropping, overlaps and empty space feel deliberate? Then remove
anything that does not strengthen it. The title and focal form must survive the thumbnail and, where
applicable, the reduced levels.

If the answer is no, revise the grid or governing idea rather than adding another motif. A cover is
not accepted until its author has viewed a render made after the last edit. Return the accepted SVG
with its one-line idea and short research trail; the main agent needs provenance but does not repeat
the creative review.

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
