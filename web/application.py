import os
import secrets
from game.world.districts import (
    DISTRICTS,
    get_district,
    get_travel_route,
)
from game.world.travel import (
    TravelError,
    get_active_travel,
    start_travel,
    update_travel,
)
from game.crime import (
    CRIMES,
    CRIMES_BY_KEY,
    commit_crime,
)
from game.gym import (
    GymError,
    VALID_BATTLE_STATS,
    calculate_training_gain,
    get_district_gyms,
    get_training_block,
    get_unlocked_gyms,
    select_gym,
    train,
    unlock_gym,
)
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
    send_password_reset_email,
    send_verification_email,
)
from auth.services.password_reset import (
    AccountTokenError,
    request_email_verification,
    request_password_reset,
    reset_password,
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
from game.housing import get_residence
from game.inventory import (
    INVENTORY_SLOT_CAPACITY,
    ITEMS,
    InventoryError,
    get_item,
    use_item,
)
from game.jobs import (
    CAREERS,
    JobError,
    complete_shift,
    get_career,
    get_job_role,
    get_shift_state,
    join_career,
    start_shift,
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


@app.route("/jobs-inventory", methods=["GET", "POST"])
def jobs_inventory():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(
        session["user_id"]
    )
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    message = None
    error = None
    active_section = request.form.get(
        "section",
        "jobs",
    )

    if request.method == "POST":
        action = request.form.get("action", "")

        try:
            if action == "join_career":
                employment = join_career(
                    player,
                    request.form.get("career_key", ""),
                )
                role = get_job_role(employment.role_key)
                message = (
                    f"Career joined. You are now "
                    f"{role.name}."
                )
            elif action == "start_shift":
                shift = start_shift(player)
                message = (
                    f"Shift started. {shift.energy_spent} "
                    f"energy used."
                )
            elif action == "complete_shift":
                completed = complete_shift(player)
                message = (
                    f"Shift complete. £{completed.salary:,} "
                    f"earned and {completed.work_xp} XP gained."
                )
                if completed.promoted_to is not None:
                    promoted = get_job_role(
                        completed.promoted_to
                    )
                    message += (
                        f" Promoted to {promoted.name}."
                    )
            elif action == "use_item":
                used = use_item(
                    player,
                    request.form.get("item_key", ""),
                )
                item = get_item(used.item_key)
                message = (
                    f"{item.name} used. "
                    f"{used.amount_restored} "
                    f"{used.effect_key} restored."
                )
            else:
                error = "Unknown action."
        except (JobError, InventoryError) as action_error:
            error = str(action_error)

    save_player(player)
    career = get_career(player.career_key)
    role = get_job_role(player.job_role_key)
    shift_state = get_shift_state(player)
    owned_items = [
        {
            "item": get_item(item_key),
            "quantity": quantity,
        }
        for item_key, quantity
        in sorted(player.inventory.items())
        if get_item(item_key) is not None
    ]

    return render_template(
        "jobs_inventory.html",
        player=player,
        careers=CAREERS,
        career=career,
        role=role,
        shift_state=shift_state,
        owned_items=owned_items,
        inventory_capacity=INVENTORY_SLOT_CAPACITY,
        active_section=active_section,
        message=message,
        error=error,
    )


@app.route("/character")
def character():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(
        session["user_id"]
    )
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    save_player(player)

    current_level_xp = xp_required_for_level(
        player.level
    )
    next_level_xp = xp_required_for_level(
        player.level + 1
    )
    xp_into_level = player.xp - current_level_xp
    xp_needed = next_level_xp - current_level_xp
    residence = get_residence(player.residence_key)

    if player.jail_until is not None:
        status = "In jail"
        status_until = player.jail_until
    elif player.hospital_until is not None:
        status = "In hospital"
        status_until = player.hospital_until
    elif player.travel_destination is not None:
        status = "Travelling"
        status_until = player.travel_until
    else:
        status = "Free"
        status_until = None

    return render_template(
        "character.html",
        player=player,
        residence=residence,
        status=status,
        status_until=status_until,
        xp_percent=percentage(
            xp_into_level,
            xp_needed,
        ),
        next_level_xp=next_level_xp,
    )


@app.route("/travel", methods=["GET", "POST"])
def travel():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(
        session["user_id"]
    )
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    arrived = update_travel(player)
    update_player_status(player)
    message = (
        f"You have arrived in "
        f"{get_district(player.current_district).name}."
        if arrived
        else None
    )
    error = None

    if request.method == "POST":
        destination_key = request.form.get(
            "destination_key",
            "",
        )
        try:
            journey = start_travel(
                player,
                destination_key,
            )
            destination = get_district(
                journey.destination_key
            )
            message = (
                f"Journey started for {destination.name}. "
                f"£{journey.cost:,} fare paid."
            )
        except TravelError as travel_error:
            error = str(travel_error)

    save_player(player)
    active_travel = get_active_travel(player)
    current = get_district(player.current_district)
    destinations = []

    if active_travel is None:
        for district in DISTRICTS:
            if district.key == current.key:
                continue

            route = get_travel_route(
                current.key,
                district.key,
            )
            destinations.append({
                "district": district,
                "cost": route.cost,
                "duration_minutes": (
                    route.duration_seconds + 59
                ) // 60,
                "locked": (
                    player.level
                    < district.minimum_level
                ),
                "affordable": (
                    player.money >= route.cost
                ),
            })

    active_destination = (
        get_district(active_travel.destination_key)
        if active_travel is not None
        else None
    )

    return render_template(
        "travel.html",
        player=player,
        current=current,
        destinations=destinations,
        active_travel=active_travel,
        active_destination=active_destination,
        message=message,
        error=error,
    )


@app.route("/gym", methods=["GET", "POST"])
def gym():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(
        session["user_id"]
    )
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    message = None
    trained_stat = None
    error = None

    if request.method == "POST":
        action = request.form.get("action", "")
        gym_key = request.form.get("gym_key", "")

        try:
            if action == "unlock":
                result = unlock_gym(player, gym_key)
                select_gym(player, gym_key)
                message = (
                    "Membership purchased for "
                    f"£{result.membership_cost:,}."
                )

            elif action == "train":
                stat = request.form.get("stat", "")
                raw_trains = request.form.get("trains")
                energy = (
                    int(raw_trains) * 10
                    if raw_trains is not None
                    else int(
                        request.form.get("energy", "0")
                    )
                )
                select_gym(player, gym_key)
                gain = calculate_training_gain(
                    gym_key,
                    stat,
                    energy,
                )
                trained = train(
                    player,
                    stat,
                    energy=energy,
                    gym_key=gym_key,
                )

                if trained:
                    trained_stat = stat
                    message = (
                        f"{stat.title()} increased by "
                        f"{gain:g}. {energy} energy used."
                    )
                else:
                    block = get_training_block(player)
                    if block:
                        error = (
                            "Training is unavailable while "
                            f"{block}."
                        )
                    else:
                        error = "Not enough energy."

            else:
                error = "Unknown gym action."

            save_player(player)

        except (ValueError, GymError) as gym_error:
            error = str(gym_error)

    gyms = get_district_gyms(
        player.current_district
    )
    return render_template(
        "gym.html",
        player=player,
        gyms=gyms,
        unlocked_gyms=get_unlocked_gyms(player),
        valid_stats=VALID_BATTLE_STATS,
        stat_descriptions={
            "strength": "Damage dealt on impact",
            "defence": "Ability to withstand damage",
            "speed": "Chance of landing an attack",
            "dexterity": "Ability to evade an attack",
        },
        max_trains=min(10, player.energy // 10),
        trained_stat=trained_stat,
        message=message,
        error=error,
        block_reason=get_training_block(player),
    )


@app.route("/crimes", methods=["GET", "POST"])
def crimes():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(
        session["user_id"]
    )
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    result = None
    attempted_crime_key = None
    error = None

    if request.method == "POST":
        crime_key = request.form.get("crime_key", "")
        attempted_crime_key = crime_key
        crime = CRIMES_BY_KEY.get(crime_key)

        if crime is None:
            error = "Crime does not exist."
        else:
            result = commit_crime(player, crime)
            save_player(player)

    district_crimes = tuple(
        crime
        for crime in CRIMES
        if crime.district.casefold()
        == player.current_district
    )
    return render_template(
        "crimes.html",
        player=player,
        crimes=district_crimes,
        result=result,
        attempted_crime_key=attempted_crime_key,
        error=error,
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


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    error = None
    notice = None
    email = ""

    if request.method == "POST":
        email = request.form.get("email", "")

        if not validate_turnstile(
            request.form.get(
                "cf-turnstile-response",
                "",
            ),
            remote_ip=request.remote_addr,
            expected_action="password_reset",
        ):
            error = (
                "Complete the human verification "
                "and try again."
            )
        else:
            try:
                result = request_password_reset(
                    email=email,
                    delivery=send_password_reset_email,
                )
                notice = result.message
            except EmailDeliveryError:
                notice = (
                    "If an account exists for that email, "
                    "recovery instructions will be sent."
                )

    return render_template(
        "forgot_password.html",
        error=error,
        notice=notice,
        email=email,
        turnstile_site_key=os.environ.get(
            "TURNSTILE_SITE_KEY",
            "",
        ),
    )


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password_route():
    raw_token = request.args.get(
        "token",
        request.form.get("token", ""),
    )
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")
        password_confirmation = request.form.get(
            "password_confirmation",
            "",
        )

        try:
            if password != password_confirmation:
                raise ValidationError(
                    "Passwords do not match."
                )

            reset_password(raw_token, password)
            return render_template(
                "verification_result.html",
                success=True,
                message=(
                    "Your password has been updated. "
                    "You can now sign in."
                ),
            )
        except (
            ValidationError,
            AccountTokenError,
        ) as reset_error:
            error = str(reset_error)

    return render_template(
        "reset_password.html",
        error=error,
        token=raw_token,
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


