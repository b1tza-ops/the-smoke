"""The pieces a handbook page is built from.

Guides are structured data rather than Markdown, which is how every
other catalogue in this project works -- items, shops, districts, gyms.
It keeps the dependency list at two, and it means a page cannot inject
markup: Jinja escapes every string, and the only formatting is the small
inline vocabulary below, applied *after* escaping.
"""

import html
import re
from dataclasses import dataclass, field
from markupsafe import Markup


@dataclass(frozen=True)
class Heading:
    text: str


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class Bullets:
    items: tuple


@dataclass(frozen=True)
class Steps:
    items: tuple


@dataclass(frozen=True)
class Table:
    headers: tuple
    rows: tuple
    caption: str = ""


@dataclass(frozen=True)
class Note:
    text: str
    tone: str = "info"


# A gallery names files inside this site's own static folder. The
# pattern is what keeps it that way: no leading slash, no scheme, and
# no `..`, so a guide cannot point the page at somewhere else.
_STATIC_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_\-]*\.(?:webp|png|svg)")


@dataclass(frozen=True)
class Gallery:
    """Pictures with captions, laid out as a strip.

    Each entry is a (filename, caption) pair. The filename is checked
    when the guide is defined rather than when the page is rendered, so
    a bad path fails at import and never reaches a reader.
    """

    images: tuple

    def __post_init__(self):
        for entry in self.images:
            filename, _caption = entry

            if not _STATIC_FILE.fullmatch(filename):
                raise ValueError(
                    f"{filename!r} is not a static file this site owns"
                )


# **bold**, `code` and [label](/path). Nothing else -- a handbook page
# does not need more, and every addition is another thing to get wrong.
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`(.+?)`")
_LINK = re.compile(r"\[([^\]]+)\]\((/[A-Za-z0-9/_\-]*)\)")


def inline(text):
    """Escape, then apply the inline vocabulary.

    Escaping first is what makes this safe: by the time any tag is
    inserted, every character that came from the source is inert.
    """
    escaped = html.escape(str(text))
    escaped = _CODE.sub(r"<code>\1</code>", escaped)
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    # Only in-site paths are linkable, so a guide cannot point somewhere
    # unexpected and no external link can be smuggled in.
    escaped = _LINK.sub(r'<a href="\2">\1</a>', escaped)
    return Markup(escaped)
