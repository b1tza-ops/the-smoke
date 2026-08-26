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
