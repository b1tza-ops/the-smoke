import os
import secrets
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from auth.validation import (
    ValidationError,
    normalize_email,
    validate_password,
    validate_username,
)
from database.core.setup import create_tables
from database.repositories.bank import BankError
from database.repositories.players import (
    create_player,
    get_player_by_user_id,
    save_player,
)
from database.repositories.users import (
    create_user,
    get_user_by_email,
    get_user_by_username,
)
from game.crime import CRIMES, commit_crime, get_crime
from game.economy.bank import deposit_cash, withdraw_cash
from game.gym import (
    GymError,
    VALID_BATTLE_STATS,
    calculate_training_gain,
    get_district_gyms,
    get_gym,
    get_training_block,
    select_gym,
    train,
    unlock_gym,
)
from game.housing import (
    RESIDENCES,
    HousingError,
    get_player_residence,
    purchase_residence,
)
from game.inventory import (
    INVENTORY_SLOT_CAPACITY,
    ITEMS,
    InventoryError,
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
from game.player.status import (
    get_active_restriction,
    update_player_status,
)
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
from utils.security import hash_password, verify_password


app = Flask(__name__)
app.config.update(
    SECRET_KEY=(
        os.environ.get("THE_SMOKE_SECRET_KEY")
        or secrets.token_hex(32)
    ),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("THE_SMOKE_SECURE_COOKIES") == "1"
    ),
)

create_tables()


def percentage(value, maximum):
    if maximum <= 0:
        return 0

    return max(
        0,
        min(100, round((value / maximum) * 100)),
    )


def parse_positive_integer(raw_value, field_name="Amount"):
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name} must be a whole number."
        ) from error

    if value <= 0:
        raise ValueError(
            f"{field_name} must be greater than zero."
        )

    return value


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


def player_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        player_data = get_player_by_user_id(
            session["user_id"]
        )

        if player_data is None:
            return redirect(url_for("create_character"))

        player = Player(*player_data)
        arrived = update_travel(player)
        status = update_player_status(player)
        save_player(player)

        if arrived:
            flash(
                f"You arrived in "
                f"{player.current_district.title()}.",
                "success",
            )

        if status.released_from_jail:
            flash("You have been released from jail.", "success")

        if status.discharged_from_hospital:
            flash(
                "You have been discharged from hospital.",
                "success",
            )

        g.player = player
        return view(*args, **kwargs)

    return wrapped


def csrf_token():
    token = session.get("_csrf_token")

    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token

    return token


@app.before_request
def protect_post_requests():
    if request.method != "POST":
        return None

    expected = session.get("_csrf_token", "")
    supplied = request.form.get("_csrf_token", "")

    if not expected or not secrets.compare_digest(
        expected,
        supplied,
    ):
        abort(400, description="Invalid form token.")

    return None


@app.context_processor
def inject_template_helpers():
    return {"csrf_token": csrf_token}


@app.template_filter("duration")
def format_duration(total_seconds):
    total_seconds = max(0, int(total_seconds or 0))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"

    return f"{minutes}m {seconds:02d}s"


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Referrer-Policy",
        "strict-origin-when-cross-origin",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "img-src 'self' data:; "
        "object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'",
    )
    return response


def dashboard_data(player):
    current_level_xp = xp_required_for_level(player.level)
    next_level_xp = xp_required_for_level(player.level + 1)
    xp_into_level = max(0, player.xp - current_level_xp)
    xp_for_next_level = max(
        1,
        next_level_xp - current_level_xp,
    )

    return {
        "health_percent": percentage(player.health, 100),
        "energy_percent": percentage(
            player.energy,
            player.max_energy,
        ),
        "nerve_percent": percentage(
            player.nerve,
            player.max_nerve,
        ),
        "xp_percent": percentage(
            xp_into_level,
            xp_for_next_level,
        ),
        "next_level_xp": next_level_xp,
    }


def render_game(template_name, active_page, **context):
    player = g.player
    return render_template(
        template_name,
        active_page=active_page,
        player=player,
        dashboard=dashboard_data(player),
        current_district=get_district(
            player.current_district
        ),
        active_travel=get_active_travel(player),
        restriction=get_active_restriction(player),
        **context,
    )


def save_and_redirect(endpoint, **values):
    save_player(g.player)
    return redirect(url_for(endpoint, **values))


@app.route("/")
@player_required
def home():
    return render_game(
        "dashboard.html",
        "dashboard",
        residence=get_player_residence(g.player),
        career=get_career(g.player.career_key),
        role=get_job_role(g.player.job_role_key),
        shift=get_shift_state(g.player),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_user_by_username(username)

        if user is None or not verify_password(password, user[3]):
            flash("Incorrect username or password.", "error")
        else:
            session.clear()
            session["user_id"] = user[0]
            session["_csrf_token"] = secrets.token_urlsafe(32)

            if get_player_by_user_id(user[0]) is None:
                return redirect(url_for("create_character"))

            return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        try:
            username = validate_username(
                request.form.get("username", "")
            )
            email = normalize_email(
                request.form.get("email", "")
            )
            password = validate_password(
                request.form.get("password", "")
            )

            if password != request.form.get(
                "password_confirm",
                "",
            ):
                raise ValidationError(
                    "The passwords do not match."
                )

            if get_user_by_username(username) is not None:
                raise ValidationError(
                    "That username is already registered."
                )

            if get_user_by_email(email) is not None:
                raise ValidationError(
                    "That email address is already registered."
                )

            user_id = create_user(
                username,
                email,
                hash_password(password),
            )
        except ValidationError as error:
            flash(str(error), "error")
        else:
            session.clear()
            session["user_id"] = user_id
            session["_csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("create_character"))

    return render_template("register.html")


@app.route("/character/create", methods=["GET", "POST"])
@login_required
def create_character():
    if get_player_by_user_id(session["user_id"]) is not None:
        return redirect(url_for("home"))

    if request.method == "POST":
        name = " ".join(
            request.form.get("name", "").split()
        )

        if not 3 <= len(name) <= 24:
            flash(
                "Character name must be 3–24 characters.",
                "error",
            )
        elif not all(
            character.isalnum()
            or character in " -'"
            for character in name
        ):
            flash(
                "Use only letters, numbers, spaces, apostrophes, or hyphens.",
                "error",
            )
        else:
            create_player(session["user_id"], name)
            flash(
                f"Welcome to London, {name}.",
                "success",
            )
            return redirect(url_for("home"))

    return render_template("create_character.html")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/gym")
@player_required
def gym_page():
    gyms = get_district_gyms(g.player.current_district)
    current_gym = get_gym(g.player.current_gym_key)
    return render_game(
        "gym.html",
        "gym",
        gyms=gyms,
        current_gym=current_gym,
        valid_stats=VALID_BATTLE_STATS,
        training_block=get_training_block(g.player),
    )


@app.post("/gym/select/<gym_key>")
@player_required
def select_gym_action(gym_key):
    try:
        if gym_key not in g.player.unlocked_gyms:
            result = unlock_gym(g.player, gym_key)
            flash(
                f"Membership purchased for "
                f"£{result.membership_cost:,}.",
                "success",
            )

        select_gym(g.player, gym_key)
        gym = get_gym(gym_key)
        flash(f"Selected {gym.name}.", "success")
    except GymError as error:
        flash(str(error), "error")

    return save_and_redirect("gym_page")


@app.post("/gym/train")
@player_required
def train_action():
    stat = request.form.get("stat", "")

    try:
        energy = parse_positive_integer(
            request.form.get("energy"),
            "Energy",
        )
        expected_gain = calculate_training_gain(
            g.player.current_gym_key,
            stat,
            energy,
        )
        trained = train(
            g.player,
            stat,
            energy=energy,
        )

        if not trained:
            block = get_training_block(g.player)
            if block:
                flash(
                    f"You cannot train while {block}.",
                    "error",
                )
            else:
                flash("You do not have enough energy.", "error")
        else:
            flash(
                f"{stat.title()} +{expected_gain:g}; "
                f"energy −{energy}.",
                "success",
            )
    except (ValueError, GymError) as error:
        flash(str(error), "error")

    return save_and_redirect("gym_page")


@app.get("/crimes")
@player_required
def crimes_page():
    return render_game(
        "crimes.html",
        "crimes",
        crimes=CRIMES,
    )


@app.post("/crimes/<crime_key>")
@player_required
def crime_action(crime_key):
    try:
        crime = get_crime(crime_key)
    except KeyError:
        abort(404)

    result = commit_crime(g.player, crime)

    if result.reason == "not_enough_nerve":
        flash("You do not have enough nerve.", "error")
    elif result.reason == "wrong_district":
        flash(
            f"Travel to {result.district} for this crime.",
            "error",
        )
    elif result.reason == "travelling":
        flash("You cannot commit crimes while travelling.", "error")
    elif result.reason:
        flash(result.reason.replace("_", " ").title(), "error")
    elif result.success:
        message = (
            f"Crime successful: £{result.cash_reward:,}, "
            f"{result.xp_reward} XP, and "
            f"{result.reputation_reward} reputation."
        )
        if result.levels_gained:
            message += f" You reached level {g.player.level}!"
        flash(message, "success")
    elif result.consequence == "jail":
        flash("Crime failed. You were sent to jail.", "error")
    elif result.consequence == "hospital":
        flash(
            f"Crime failed. You took {result.damage} damage "
            "and were hospitalized.",
            "error",
        )
    else:
        flash(
            f"Crime failed. You took {result.damage} damage.",
            "error",
        )

    return save_and_redirect("crimes_page")


@app.get("/jobs")
@player_required
def jobs_page():
    return render_game(
        "jobs.html",
        "jobs",
        careers=CAREERS,
        career=get_career(g.player.career_key),
        role=get_job_role(g.player.job_role_key),
        shift=get_shift_state(g.player),
    )


@app.post("/jobs/join/<career_key>")
@player_required
def join_career_action(career_key):
    try:
        result = join_career(g.player, career_key)
        role = get_job_role(result.role_key)
        career = get_career(result.career_key)
        flash(
            f"You joined {career.name} as {role.name}.",
            "success",
        )
    except JobError as error:
        flash(str(error), "error")

    return save_and_redirect("jobs_page")


@app.post("/jobs/shift/start")
@player_required
def start_shift_action():
    try:
        result = start_shift(g.player)
        flash(
            f"Shift started. {result.energy_spent} energy used; "
            f"finishes at {result.completes_at} UTC.",
            "success",
        )
    except JobError as error:
        flash(str(error), "error")

    return save_and_redirect("jobs_page")


@app.post("/jobs/shift/complete")
@player_required
def complete_shift_action():
    try:
        result = complete_shift(g.player)
        message = (
            f"Shift complete: £{result.salary:,} and "
            f"{result.work_xp} XP earned."
        )
        if result.promoted_to:
            message += (
                f" Promoted to "
                f"{get_job_role(result.promoted_to).name}!"
            )
        flash(message, "success")
    except JobError as error:
        flash(str(error), "error")

    return save_and_redirect("jobs_page")


@app.get("/inventory")
@player_required
def inventory_page():
    owned_items = [
        (item, g.player.inventory.get(item.key, 0))
        for item in ITEMS
        if g.player.inventory.get(item.key, 0) > 0
    ]
    return render_game(
        "inventory.html",
        "inventory",
        owned_items=owned_items,
        capacity=INVENTORY_SLOT_CAPACITY,
    )


@app.post("/inventory/use/<item_key>")
@player_required
def use_item_action(item_key):
    try:
        result = use_item(g.player, item_key)
        flash(
            f"Item used: {result.effect_key.title()} "
            f"+{result.amount_restored}.",
            "success",
        )
    except InventoryError as error:
        flash(str(error), "error")

    return save_and_redirect("inventory_page")


@app.get("/bank")
@player_required
def bank_page():
    return render_game("bank.html", "bank")


@app.post("/bank/<action>")
@player_required
def bank_action(action):
    try:
        amount = parse_positive_integer(
            request.form.get("amount"),
        )

        if action == "deposit":
            result = deposit_cash(g.player, amount)
            verb = "Deposited"
        elif action == "withdraw":
            result = withdraw_cash(g.player, amount)
            verb = "Withdrew"
        else:
            abort(404)

        flash(
            f"{verb} £{result.amount:,} successfully.",
            "success",
        )
    except (ValueError, BankError) as error:
        flash(str(error), "error")

    return save_and_redirect("bank_page")


@app.get("/travel")
@player_required
def travel_page():
    destinations = []

    if get_active_travel(g.player) is None:
        for district in DISTRICTS:
            if district.key == g.player.current_district:
                continue

            destinations.append(
                (
                    district,
                    get_travel_route(
                        g.player.current_district,
                        district.key,
                    ),
                )
            )

    return render_game(
        "travel.html",
        "travel",
        destinations=destinations,
    )


@app.post("/travel/<destination_key>")
@player_required
def travel_action(destination_key):
    try:
        result = start_travel(g.player, destination_key)
        destination = get_district(result.destination_key)
        flash(
            f"Travelling to {destination.name}. "
            f"Fare £{result.cost:,}; arrival "
            f"{result.arrives_at} UTC.",
            "success",
        )
    except (TravelError, KeyError) as error:
        flash(str(error), "error")

    return save_and_redirect("travel_page")


@app.get("/housing")
@player_required
def housing_page():
    return render_game(
        "housing.html",
        "housing",
        residences=RESIDENCES,
        residence=get_player_residence(g.player),
    )


@app.post("/housing/<residence_key>")
@player_required
def housing_action(residence_key):
    try:
        result = purchase_residence(
            g.player,
            residence_key,
        )
        residence = get_player_residence(g.player)
        flash(
            f"You moved into {residence.name} for "
            f"£{result.amount_paid:,}.",
            "success",
        )
    except HousingError as error:
        flash(str(error), "error")

    return save_and_redirect("housing_page")


@app.errorhandler(400)
def bad_request(error):
    return render_template(
        "error.html",
        code=400,
        message=getattr(
            error,
            "description",
            "The request could not be processed.",
        ),
    ), 400


@app.errorhandler(404)
def not_found(_error):
    return render_template(
        "error.html",
        code=404,
        message="That part of London could not be found.",
    ), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template(
        "error.html",
        code=500,
        message="The city hit a problem. Your last saved state is safe.",
    ), 500
