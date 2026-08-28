<p align="center">
  <img src="./assets/galley-logo.png" alt="Galley" width="200">
</p>

# Galley

Galley turns web articles and Markdown into EPUBs compatible with your e-ink reader.

Tell your agent what you want to read; Galley gives it the tools and instructions to
do the work.


It currently knows two targets: 
- Xteink X4 running [CrossPoint](https://crosspointreader.com/)
- Kindle personal documents shared through Kindle for iOS.

## Inspiration

Between web extractors and converters such as Pandoc, turning Markdown or a URL into a valid EPUB
is the easy part. Plain conversion even handles ordinary prose well. But valid is not the same as
readable: code, tables, footnotes, images, and navigation are where generic conversion starts to
fall apart.

E-ink readers are wonderfully opinionated little machines. A book can pass EPUBCheck while its
footnotes fail, its images disappear, or its content is silently lost on the device in your hand.
Galley sniffs those quirks out: device behaviour lives in small profiles, every conversion explains
itself, and uncertain calls stay with you.

## Quick start

Install Galley 0.1.0 from its tagged GitHub release with
[uv](https://docs.astral.sh/uv/):

```sh
uv tool install "git+https://github.com/fxn-m/galley.git@v0.1.0"
galley skill install
```

The last command installs Galley's two matching Agent Skills: `galley` runs the reading workflow,
and `galley-setup` handles the first conversation. Use `--target` if your agent reads skills from a
different directory.

Put the pinned command-line tools on your `PATH`: Pandoc 3.10, Defuddle 0.19.1, EPUBCheck 5.3.0
(with Java), and resvg 0.48.1. Defuddle can be installed with
`npm install --global defuddle@0.19.1`.

## First run

Open your coding agent and say:

> Set up Galley.

The Setup Skill asks six short questions about your workspace, reading folders, and device. If the
suggested setup suits you, answer **“all defaults”** and confirm once. It writes a small, visible
configuration file, creates only Galley's own working folders, and checks the result for you.

Then try:

> Prepare this article for my X4 with Galley.

Or, for a reading folder:

> Galley my inbox.

The main skill checks what is new, prepares the straightforward books, keeps useful evidence when
something needs attention, and shows you exactly what it wants to deliver before asking for one
approval.

The CLI is still available directly when you want it:

```sh
galley profiles list
galley prepare article.md --profile x4-crosspoint --output article.epub
```

An Article-Like Page URL can be used in place of `article.md`.

## How it works

Your agent starts by inspecting the source. If the journey is routine, it prepares the book. If
meaning or structure needs repair, it makes a separate, reversible repair and asks you before
making an ambiguous editorial choice.

Underneath that conversation, Galley applies only the changes selected for the reading device,
builds an EPUB3, and checks the finished book. It leaves a plain record of what changed, what was
measured, and what still needs an agent or a person to judge.

The original source is never edited. Network access is explicit, and delivery to an X4 stays on
the local network.

Galley is early, empirical software. Its profiles describe the devices and versions that were
actually observed; they are not promises about every e-reader.

MIT licensed.
