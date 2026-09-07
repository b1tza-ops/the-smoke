"""When each guide last actually changed.

`<lastmod>` is the one hint in a sitemap that Google says it uses.
`priority` and `changefreq` it ignores outright -- so the sitemap was
sending two signals that are discarded and omitting the one that is
read.

The difficulty with `lastmod` is that a wrong one is worse than none.
Google's guidance is explicit: a date that is always "now", or that
moves on every deploy, gets the whole field ignored for the site. So it
cannot be the file's modification time, because a git checkout stamps
every file at deploy time and would claim the entire handbook changed
on every release.

So the date is written down, and a fingerprint of the guide is written
down beside it. `tests/gameplay/test_handbook.py` recomputes the
fingerprint and fails if a guide's words have changed without its date
moving -- which makes the date true by construction rather than by
somebody remembering.

To change a guide: edit it, run the tests, and paste the fingerprint
and today's date that the failure prints.
"""

import hashlib

from game.handbook.blocks import Bullets, Note, Steps, Table, Text


def fingerprint(guide):
    """A stable hash of everything a reader sees on the page.

    Title and summary are included, because those are the page's
    `<title>` and `<meta description>`: changing either changes what a
    search engine has indexed just as much as changing a paragraph.
    """
    parts = [guide.title, guide.summary]

    for block in guide.blocks:
        if isinstance(block, (Text, Note)):
            parts.append(str(block.text))
        elif isinstance(block, (Bullets, Steps)):
            parts.extend(str(item) for item in block.items)
        elif isinstance(block, Table):
            parts.extend(str(header) for header in block.headers)
            parts.append(str(block.caption))
            for row in block.rows:
                parts.extend(str(cell) for cell in row)
        else:
            parts.append(str(getattr(block, "text", "")))

    joined = " ".join(parts).encode("utf-8")

    return hashlib.sha256(joined).hexdigest()[:16]


# The first date anybody can honestly claim for the handbook: the day
# the freshness data was added. A guide edited after this carries the
# day it changed, and the fingerprint beside it is what proves the
# claim.
HANDBOOK_EPOCH = "2026-09-03"

# slug -> (last changed, fingerprint on that date)
GUIDE_FRESHNESS = {
    "first-hour": ("2026-09-03", "bb11e97463c3acfa"),
    "energy-and-nerve": ("2026-09-03", "030ef9578db4075f"),
    "crime-and-jail": ("2026-09-03", "c0d9994cfc2b49a8"),
    "selling-what-you-steal": ("2026-09-03", "73272dee0910f95a"),
    "the-gym": ("2026-09-03", "b5f9dbb019e02174"),
    "fighting": ("2026-09-03", "d4f1765ad39e1347"),
    "guns-and-ammunition": ("2026-09-03", "c4fe492958c6d044"),
    "jobs-and-shifts": ("2026-09-03", "61f72aa4f358a2d1"),
    "the-item-market": ("2026-09-03", "dcc29243a35e87ef"),
    "daily-contracts": ("2026-09-03", "0f1a92a11eaa94e3"),
    "travel": ("2026-09-03", "70fab60cc4eda6e8"),
    "the-casino": ("2026-09-03", "550e91341652245f"),
    "the-loan-shark": ("2026-09-03", "9ffa4b5466f9c890"),
    "housing": ("2026-09-03", "80e01f06a497f861"),
}


def last_changed(guide):
    entry = GUIDE_FRESHNESS.get(guide.slug)

    return entry[0] if entry else HANDBOOK_EPOCH
