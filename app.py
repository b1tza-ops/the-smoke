import os
import secrets
from game.world.travel import update_travel
from flask import Flask, render_template, request, redirect, session
from database.setup import create_tables
from database.users import get_user_by_username

from database.players import (
    get_player_by_user_id,
    save_player,
)

from utils.security import verify_password
from game.player import Player
from game.player.progression import xp_required_for_level
from game.player.status import update_player_status


app = Flask(__name__)

app.config.update(
    SECRET_KEY=os.environ.get("THE_SMOKE_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

create_tables()


def percentage(value, maximum):
    if maximum <= 0:
        return 0

    return max(0, min(100, round((value / maximum) * 100)))


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(session["user_id"])

    if player_data is None:
        return "No character found."

    player = Player(*player_data)

    update_travel(player)
    update_player_status(player)

    save_player(player)
    current_level_xp = xp_required_for_level(player.level)
    next_level_xp = xp_required_for_level(player.level + 1)
    xp_into_level = player.xp - current_level_xp
    xp_for_next_level = next_level_xp - current_level_xp

    dashboard = {
        "health_percent": percentage(player.health, 100),
        "energy_percent": percentage(player.energy, player.max_energy),
        "nerve_percent": percentage(player.nerve, player.max_nerve),
        "xp_percent": percentage(xp_into_level, xp_for_next_level),
        "next_level_xp": next_level_xp,
    }

    return render_template(
        "dashboard.html",
        player=player,
        dashboard=dashboard,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = get_user_by_username(username)

        if user is None:
            error = "User not found."

        elif not verify_password(password, user[3]):
            error = "Incorrect password."

        else:
            session["user_id"] = user[0]
            return redirect("/")

    return render_template(
        "login.html",
        error=error
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
