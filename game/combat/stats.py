"""Whole-number stats, for the parts of combat that require them.

Training produces fractional stats on purpose -- `game/gym/formula.py`
rounds each gain to two decimal places, so a trained player's strength
is 84.35 rather than 84. That precision is right for the gym and wrong
everywhere it meets `random.randint`, which needs an integer.

Python used to hide this. Until 3.12, `random.randrange` accepted a
float that happened to be whole, so `randint(0, 84.0)` worked and
`randint(0, 84.35)` raised. 3.12 removed the allowance entirely and
3.14 raises TypeError on both. Production runs 3.14; a development
machine on 3.11 will not reproduce it for any player whose stats happen
to be whole numbers.

Rounding rather than truncating, so 84.9 is treated as 85 and a player
is never quietly shorted the fraction they trained for.
"""


def whole(value):
    """A stat as an integer, safe to hand to randint and to print."""
    return int(round(value or 0))
