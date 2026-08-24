import os
import secrets
from game.world.travel import update_travel
from flask import Flask, render_template, request, redirect, session
from database.core.setup import create_tables
from database.repositories.users import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    is_email_verified,
)
from database.repositories.presence import (
    get_online_player_count,
    mark_player_offline,
    mark_player_online,
)

from database.repositories.players import (
    create_player,
    get_player_by_user_id,
    save_player,
)

from auth.email_delivery import (
    EmailDeliveryError,
    send_verification_email,
)
from auth.services.password_reset import (
    AccountTokenError,
    request_email_verification,
    verify_email_token,
)
from auth.turnstile import validate_turnstile
from auth.validation import (
    ValidationError,
    normalize_email,
    validate_password,
    validate_username,
)
from utils.security import (
    hash_password,
    verify_password,
)
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


@app.before_request
def record_authenticated_activity():
    if "user_id" in session:
        mark_player_online(session["user_id"])


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
        online_players=get_online_player_count(),
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect("/")

    error = None
    form_data = {
        "username": "",
        "email": "",
    }

    if request.method == "POST":
        form_data["username"] = request.form.get(
            "username",
            "",
        )
        form_data["email"] = request.form.get(
            "email",
            "",
        )
        password = request.form.get("password", "")
        password_confirmation = request.form.get(
            "password_confirmation",
            "",
        )

        try:
            if not validate_turnstile(
                request.form.get(
                    "cf-turnstile-response",
                    "",
                ),
                remote_ip=request.remote_addr,
                expected_action="register",
            ):
                raise ValidationError(
                    "Complete the human verification "
                    "and try again."
                )

            username = validate_username(
                form_data["username"]
            )
            email = normalize_email(form_data["email"])
            password = validate_password(password)

            if password != password_confirmation:
                raise ValidationError(
                    "Passwords do not match."
                )

            if get_user_by_username(username):
                raise ValidationError(
                    "Username already taken."
                )

            if get_user_by_email(email):
                raise ValidationError(
                    "Email already registered."
                )

            user_id = create_user(
                username,
                email,
                hash_password(password),
            )
            create_player(user_id, username)
            session[
                "pending_verification_user_id"
            ] = user_id

            try:
                request_email_verification(
                    user_id=user_id,
                    email=email,
                    delivery=send_verification_email,
                )
                session["verification_notice"] = (
                    "Verification email sent. Check your "
                    "inbox and spam folder."
                )
            except EmailDeliveryError:
                session["verification_notice"] = (
                    "Your account was created, but the "
                    "verification email could not be sent. "
                    "Use the resend button below."
                )

            return redirect("/check-email")

        except ValidationError as validation_error:
            error = str(validation_error)

    return render_template(
        "register.html",
        error=error,
        form_data=form_data,
        turnstile_site_key=os.environ.get(
            "TURNSTILE_SITE_KEY",
            "",
        ),
    )


@app.route("/check-email")
def check_email():
    user_id = session.get(
        "pending_verification_user_id"
    )
    user = get_user_by_id(user_id) if user_id else None

    if user is None:
        return redirect("/register")

    if user[5]:
        return redirect("/login")

    notice = session.pop(
        "verification_notice",
        None,
    )
    return render_template(
        "check_email.html",
        email=user[2],
        notice=notice,
        error=None,
    )


@app.route("/resend-verification", methods=["POST"])
def resend_verification():
    user_id = session.get(
        "pending_verification_user_id"
    )
    user = get_user_by_id(user_id) if user_id else None

    if user is None:
        return redirect("/register")

    if user[5]:
        return redirect("/login")

    try:
        request_email_verification(
            user_id=user[0],
            email=user[2],
            delivery=send_verification_email,
        )
        notice = (
            "A new verification email has been sent."
        )
        error = None
    except EmailDeliveryError:
        notice = None
        error = (
            "The email could not be sent. "
            "Please try again shortly."
        )

    return render_template(
        "check_email.html",
        email=user[2],
        notice=notice,
        error=error,
    )


@app.route("/verify-email")
def verify_email():
    raw_token = request.args.get("token", "")

    try:
        verify_email_token(raw_token)
        session.pop(
            "pending_verification_user_id",
            None,
        )
        return render_template(
            "verification_result.html",
            success=True,
            message=(
                "Your email is verified. "
                "You can now sign in."
            ),
        )
    except AccountTokenError as token_error:
        return render_template(
            "verification_result.html",
            success=False,
            message=str(token_error),
        ), 400


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

        elif not is_email_verified(user[0]):
            session[
                "pending_verification_user_id"
            ] = user[0]
            session["verification_notice"] = (
                "Verify your email before signing in."
            )
            return redirect("/check-email")

        else:
            session["user_id"] = user[0]
            return redirect("/")

    return render_template(
        "login.html",
        error=error
    )


@app.route("/logout")
def logout():
    if "user_id" in session:
        mark_player_offline(session["user_id"])

    session.clear()
    return redirect("/login")


