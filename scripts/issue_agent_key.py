#!/usr/bin/env python3
"""Declare an account a machine and print its key.

Deliberately a script rather than a page. Making an account an agent
seals it off from every other player permanently-ish, and lets it play
unattended; that is an owner's decision taken at a terminal, not
something anybody should be able to do to themselves from a form.

    python3 scripts/issue_agent_key.py <username> "Claude, first try"
    python3 scripts/issue_agent_key.py --revoke <username>

The key is printed once. It is stored only as a hash, so a lost key is
reissued rather than recovered.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.core.setup import create_tables
from database.repositories.agents import issue_key, revoke_key
from database.repositories.users import get_user_by_username
from game.agents.service import AgentError, AGENT_SEALED_ACTIONS


def main(argv):
    create_tables()

    revoking = "--revoke" in argv
    argv = [item for item in argv if item != "--revoke"]

    if not argv:
        print(__doc__)
        return 2

    username = argv[0]
    user = get_user_by_username(username)

    if user is None:
        print(f"No account called {username!r}.")
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
    print("This account can no longer " + ", ".join(AGENT_SEALED_ACTIONS)
          + " -- and no player can do those to it either.")
    print("Point it at /api/v1 and it will tell itself how to play.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
