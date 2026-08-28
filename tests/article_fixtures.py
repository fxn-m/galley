"""The pinned Article-Like Pages behavioural tests are measured against.

Each document is authored for one question and says so. Every one clears the Extraction Failure
threshold, because a fixture below it measures that rule instead of what it was written for.
The loopback server that serves them lives in `tests.article_server`.
"""

ARTICLE_PATH = "/essay"
ENCODING = "utf-8"
# Article extraction refuses fewer than 300 reader-visible words, so any fixture written to
# measure something else has to clear that threshold. Filler is distinct-worded and inert: it
# carries no link, note, image or entity, so it cannot affect what the fixture was written to show.
BODY_WORDS = 320


def filler_words(words: int = BODY_WORDS) -> str:
    """The bare words, so a Markdown fixture and an article fixture can carry the same text."""

    return " ".join(f"filler{index}" for index in range(words))


def filler(words: int = BODY_WORDS) -> str:
    """One paragraph of distinct words, long enough to keep a fixture out of the rule's way."""

    return f"<p>{filler_words(words)}</p>"


# One small Article-Like Page: a title, an author, prose Defuddle keeps, and the site chrome it
# removes. The prose is what every extraction assertion is measured against.
ARTICLE = """<!doctype html>
<html><head>
<title>A Small Essay</title>
<meta name="author" content="Ada Lovelace">
</head><body>
<nav><a href="/one">One</a><a href="/two">Two</a></nav>
<article>
<h1>A Small Essay</h1>
<p>Enginewise the analytical machine weaves algebraic patterns exactly as the loom weaves
flowers and leaves, and the substance of that comparison is the whole argument here.</p>
<h2>A section inside it</h2>
<p>Numbers are not the only quantities the engine may order and combine, provided their mutual
relations can be expressed by the abstract science of operations.</p>
{filler}
</article>
<footer><p>Copyright chrome nobody reads.</p></footer>
</body></html>
""".replace("{filler}", filler())

# The reader-visible words the essay above carries, in the order Defuddle keeps them.
ARTICLE_WORDS = ("Enginewise", "algebraic", "loom", "quantities", "operations")

# Defuddle's normalised footnote shape, authored directly because Defuddle passes it through
# unchanged: a `sup` reference wrapping an anchor at `#fn:N`, and an `#footnotes` container of
# `li` definitions. Pandoc's HTML reader ignores it until both halves are relabelled.
APPARATUS = """<!doctype html>
<html><head><title>An Essay With Notes</title></head><body>
<article><h1>An Essay With Notes</h1>
<p>Alpha bravo charlie delta echo foxtrot.<sup id="fnref:1"><a href="#fn:1">1</a></sup></p>
<p>Golf hotel india juliet kilo lima.<sup id="fnref:2"><a href="#fn:2">2</a></sup></p>
<div id="footnotes"><ol>
<li id="fn:1">Firstnote body here. <a class="footnote-backref" href="#fnref:1">&#8617;</a></li>
<li id="fn:2">Secondnote body here. <a class="footnote-backref" href="#fnref:2">&#8617;</a></li>
</ol></div>
</article></body></html>
""".replace("<div id=", filler() + "\n<div id=")

# The same references with no container at all, which is what a page whose targets extraction
# dropped looks like. Two references, zero definitions.
APPARATUS_WITHOUT_TARGETS = APPARATUS.replace(
    """<div id="footnotes"><ol>
<li id="fn:1">Firstnote body here. <a class="footnote-backref" href="#fnref:1">&#8617;</a></li>
<li id="fn:2">Secondnote body here. <a class="footnote-backref" href="#fnref:2">&#8617;</a></li>
</ol></div>
""",
    "",
)

# Two references, one definition. Recovery would leave the second reference pointing at nothing.
APPARATUS_MISMATCHED = APPARATUS.replace(
    """<li id="fn:2">Secondnote body here. <a class="footnote-backref" href="#fnref:2">&#8617;</a></li>\n""",
    "",
)

# Two references and two definitions, one of which carries no reader-visible text. Galley refuses
# the whole recovery rather than shipping a note that opens on a blank page.
APPARATUS_WITH_EMPTY_NOTE = APPARATUS.replace(
    """<li id="fn:2">Secondnote body here. <a class="footnote-backref" href="#fnref:2">&#8617;</a></li>""",
    """<li id="fn:2"><a class="footnote-backref" href="#fnref:2">&#8617;</a></li>""",
)

# Every definition here plainly carries text, and one of them also carries a stray `<li>` inside
# its `<p>`. Pandoc's HTML5 parser restructures the list around that item and **every** note comes
# out empty, including the well-formed one — which is why emptiness cannot be read off the markup.
# An observed article shipped seventeen blank footnote pages this way.
APPARATUS_WITH_STRAY_ITEM = APPARATUS.replace(
    """<li id="fn:2">Secondnote body here.""",
    """<li id="fn:2"><p><li>Secondnote body here.</li>""",
)

# One note spanning two paragraphs, which the recognised shape carries and the relabel must keep.
APPARATUS_MULTI_PARAGRAPH = """<!doctype html>
<html><head><title>An Essay With A Long Note</title></head><body>
<article><h1>An Essay With A Long Note</h1>
<p>Alpha bravo charlie delta echo.<sup id="fnref:1"><a href="#fn:1">1</a></sup></p>
<div id="footnotes"><ol>
<li id="fn:1"><p>Firstpara body here.</p><p>Secondpara body here.</p></li>
</ol></div>
</article></body></html>
""".replace("<div id=", filler() + "\n<div id=")


def words_article(count: int) -> str:
    """Build an Article-Like Page whose extracted baseline holds exactly `count` word tokens.

    Every word is distinct, so a count is a count rather than a multiset that happens to total
    right. The heading contributes none of them: Defuddle promotes a leading `h1` matching the
    title into metadata and removes it from the content, which is measured rather than assumed.
    """

    body = " ".join(f"word{index}" for index in range(count))
    return (
        "<!doctype html>\n<html><head><title>Countable</title></head><body>\n"
        "<article><h1>Countable</h1>\n"
        f"<p>{body}</p>\n"
        "</article></body></html>\n"
    )


# An in-book link whose href looks like a reference but which sits in ordinary prose with no
# container behind it. Defuddle keeps it, and it must be left exactly as it is.
LOOKALIKE_LINKS = """<!doctype html>
<html><head><title>An Essay Without Notes</title></head><body>
<article><h1>An Essay Without Notes</h1>
<p>Alpha bravo charlie delta echo foxtrot <a href="#fn:1">see note</a> here.</p>
<p>Golf hotel india juliet kilo lima mike november.</p>
</article></body></html>
""".replace("</article>", filler() + "\n</article>")


# One paragraph of prose carrying a web link and a footnote reference, written twice: once as
# Markdown and once as the shape Defuddle produces. The two are equivalent after extraction, which
# is what makes their downstream treatment comparable.
PAIRED_PROSE = "Alpha bravo charlie delta echo foxtrot golf hotel india juliet."
PAIRED_LINK_TEXT = "an outbound link"
PAIRED_LINK_HREF = "https://example.com/away"
PAIRED_NOTE = "Firstnote body here."
PAIRED_TITLE = "A Paired Document"


def paired_markdown() -> str:
    """The Markdown half of the pair: one note, one web link, one heading, shared filler."""

    return (
        f"---\ntitle: {PAIRED_TITLE}\n---\n\n"
        f"# {PAIRED_TITLE}\n\n"
        f"{PAIRED_PROSE} [{PAIRED_LINK_TEXT}]({PAIRED_LINK_HREF}) and a reference.[^1]\n\n"
        f"[^1]: {PAIRED_NOTE}\n\n"
        f"{filler_words()}\n"
    )


def paired_article() -> str:
    """The Article-Like Page half of the pair, in the shape the relabeller recognises."""

    return (
        f"<!doctype html>\n<html><head><title>{PAIRED_TITLE}</title></head><body>\n"
        f"<article><h1>{PAIRED_TITLE}</h1>\n"
        f'<p>{PAIRED_PROSE} <a href="{PAIRED_LINK_HREF}">{PAIRED_LINK_TEXT}</a> and a '
        'reference.<sup id="fnref:1"><a href="#fn:1">1</a></sup></p>\n'
        f"{filler()}\n"
        f'<div id="footnotes"><ol><li id="fn:1">{PAIRED_NOTE}</li></ol></div>\n'
        "</article></body></html>\n"
    )


def illustrated_article(src: str) -> str:
    """One Article-Like Page carrying a single image reference, long enough to clear the rule."""

    return (
        "<!doctype html>\n<html><head><title>An Illustrated Essay</title></head><body>\n"
        "<article><h1>An Illustrated Essay</h1>\n"
        "<p>Alpha bravo charlie delta echo foxtrot golf hotel india.</p>\n"
        f'<p><img src="{src}" alt="a figure the essay explains"></p>\n'
        f"{filler()}\n"
        "</article></body></html>\n"
    )
