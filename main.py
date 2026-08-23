"""Command-line game entrypoint."""

from cli.application import game_menu, load_or_create_player, main

__all__ = ["game_menu", "load_or_create_player", "main"]


if __name__ == "__main__":
    main()
