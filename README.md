<p align="center">
  <img src="./assets/galley-logo.png" alt="Galley" width="200">
</p>

# Galley

Galley turns web articles and Markdown into EPUBs compatible with your e-ink reader.

Tell your agent what you want to read; Galley gives it the tools and instructions to
do the work.

It currently knows two targets:

- Xteink X4 running [CrossPoint](https://crosspointreader.com/)
- Kindle

## Inspiration

With web extractors such as [Defuddle](https://github.com/kepano/defuddle), and converters such as [Pandoc](https://pandoc.org/), turning Markdown or a URL into a valid EPUB is straightforward.

But _valid_ is not the same as _readable_: hierarchy, code, tables, footnotes, images, callouts, and navigation are where generic conversion starts to fall apart.

E-ink readers are wonderfully opinionated little machines. A book can pass [EPUBCheck](https://www.w3.org/publishing/epubcheck/) while its footnotes fail, its images disappear,
or its content is silently lost on the device in your hand.

Galley sniffs those quirks out: device behaviour lives in profiles, tooling flags violations, your agent can make surgical repairs, and uncertain calls stay with you.

## Quick start

Install Galley from GitHub with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install "git+https://github.com/fxn-m/galley.git"
galley skill install
```

The last command installs Galley's two Agent Skills:

- `galley-setup` handles the first conversation
- `galley` runs the main workflow

Galley is tested on macOS. Linux and Windows support is currently experimental.

## First run

Open your coding agent and say:

```
Set up Galley.
```

The Setup Skill first checks Galley's pinned dependencies. If anything is absent or at another
version, your agent chooses the exact installation route for your machine, shows the complete plan
once, then performs and verifies it after your approval.

Then try:

```
Galley the-silmarillion.md
```

Or, for an article on the web:

```
Galley https://mitchellh.com/writing/my-ai-adoption-journey
```

Or, for a reading folder:

```
Galley my inbox.
```

The main skill checks what is new, prepares the straightforward books, keeps useful evidence when
something needs attention, and shows you exactly what it wants to deliver before asking for one
approval.

The CLI is still available directly when you want it:

```sh
galley profiles list
galley prepare the-silmarillion.md --profile x4-crosspoint --output the-silmarillion-x4.epub
galley prepare https://mitchellh.com/writing/my-ai-adoption-journey --profile kindle-ios-personal-documents --output my-ai-adoption-journey.epub
```

## How it works

Your agent starts by inspecting the source. If the conversion is routine, it prepares the book. If
meaning or structure needs repair, it makes a separate, reversible repair and will ask you before
making an ambiguous editorial choice.

Underneath that conversation, Galley applies only the changes selected for the reading device,
builds an EPUB3, and checks the finished book. It leaves a plain record of what changed, what was
measured, and what still needs an agent or a person to judge.

The original source is never edited. Network access is explicit, and delivery to an X4 stays on
the local network.

**Galley is very much a work in progress.**

MIT licensed.
