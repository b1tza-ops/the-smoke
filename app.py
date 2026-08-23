"""Flask development entrypoint."""

import os

from web.application import app

__all__ = ["app"]


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
