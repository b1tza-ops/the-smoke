"""The handbook: guides at /forum, and the rules at /rules.

Content is structured data rather than Markdown or database rows. That
keeps the dependency list at two, means a page cannot inject markup, and
puts every edit through the same review as any other change. It also
matches how the rest of this project stores catalogues.

Nothing here is player-writable. If player posting is ever wanted, the
place to add it is a new module beside this one -- these pages stay
staff-published either way.
"""

from game.handbook.blocks import (
    Bullets,
    Heading,
    Note,
    Steps,
    Table,
    Text,
    inline,
)
from game.handbook.guides import (
    GUIDES,
    GUIDES_BY_SLUG,
    SECTION_ORDER,
    Guide,
    get_guide,
    sections,
)
from game.handbook.rules import CLOSING, INTRO, RULES, RULES_BY_KEY, Rule

__all__ = [
    "Bullets",
    "CLOSING",
    "GUIDES",
    "GUIDES_BY_SLUG",
    "Guide",
    "Heading",
    "INTRO",
    "Note",
    "RULES",
    "RULES_BY_KEY",
    "Rule",
    "SECTION_ORDER",
    "Steps",
    "Table",
    "Text",
    "get_guide",
    "inline",
    "sections",
]
