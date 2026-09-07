#!/usr/bin/env python3
"""Declare an account a machine and print its key.

Deliberately a script rather than a page. Making an account an agent
seals it off from every other player, and lets it play unattended; that
is an owner's decision taken at a terminal, not something anybody
should be able to do to themselves from a form.

Usage:

    python3 scripts/issue_agent_key.py                      list accounts
    python3 scripts/issue_agent_key.py USERNAME "A name"     issue a key
    python3 scripts/issue_agent_key.py --revoke USERNAME     take it back

Type a real username in place of USERNAME. The usage line used to read
`<username>`, which is a shell redirect the moment anybody pastes it --
the first thing this script ever did in anger was fail on its own
documentation.

The key is printed once. It is stored only as a hash, so a lost key is
reissued rather than recovered.
"""

import sys
from difflib import get_close_matches
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.core.setup import create_tables
from database.repositories.agents import accounts, issue_key, revoke_key
from database.repositories.users import get_user_by_username
from game.agents.service import AGENT_SEALED_ACTIONS, AgentError


def show_accounts(highlight=None):
    """Print who exists, so nobody has to guess at a name."""
    roll = accounts()

    if not roll:
        print("No accounts with a character yet.")
        return

    agents = [row for row in roll if row["is_agent"]]

    print(f"{len(roll)} account(s) on this server:")
    print()
    for row in roll:
        mark = "  agent" if row["is_agent"] else "       "
        label = f"  ({row['agent_label']})" if row["is_agent"] else ""
        print(
            f" {mark}  {row['username']:<24}"
            f"level {row['level']}{label}"
        )
    print()

    if agents:
        print(f"{len(agents)} of them already play through the API.")
    else:
        print("None of them are agents yet.")

    if highlight:
        near = get_close_matches(
            highlight, [row["username"] for row in roll], n=3
        )
        if near:
            print()
            print("Did you mean: " + ", ".join(near) + "?")


def main(argv):
    create_tables()

    revoking = "--revoke" in argv
    argv = [item for item in argv if not item.startswith("--")]

    if not argv:
        print(__doc__.strip().split("Usage:")[1].strip())
        print()
        show_accounts()
        return 0

    username = argv[0]

    if username.startswith("<") or username.endswith(">"):
        print(
            f"{username!r} looks like the placeholder from the usage "
            "line rather than a name."
        )
        print("Type a real username, without the angle brackets.")
        print()
        show_accounts()
        return 2

    user = get_user_by_username(username)

    if user is None:
        print(f"No account called {username!r}.")
        print()
        show_accounts(highlight=username)
        return 1

    user_id = user[0]

    if revoking:
        if revoke_key(user_id):
            print(f"{username} is no longer an agent.")
            return 0

        print(f"{username} was not an agent.")
        return 1

    label = argv[1] if len(argv) > 1 else username

    try:
        key = issue_key(user_id, label)
    except AgentError as error:
        print(str(error))
        return 1

    print(f"{username} is now an agent: {label}")
    print()
    print(f"  {key}")
    print()
    print("Shown once. Store it now; it cannot be recovered.")
    print()
    print(
        "This account can no longer "
        + ", ".join(AGENT_SEALED_ACTIONS)
        + " -- and no player can do those to it either."
    )
    print("Point it at /api/v1 and it will tell itself how to play:")
    print()
    print(f'  curl -H "Authorization: Bearer {key}" \\')
    print("       https://play.the-smoke.com/api/v1/actions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
