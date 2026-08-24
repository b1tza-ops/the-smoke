import hmac
import logging
import os
import secrets
import sqlite3
from datetime import timedelta
from functools import wraps
from logging.handlers import RotatingFileHandler
from types import SimpleNamespace
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
from game.combat import (
    COMBAT_ENERGY_COST,
    OPPONENTS_BY_KEY,
    CombatError,
    fight_opponent,
    get_combat_block,
    get_district_opponents,
    get_encounter_records,
    record_encounter,
    APPROACHES,
    PVP_ENERGY_COST,
    PvpError,
    estimate_target,
    fight_player,
    get_pvp_block,
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
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
)
from database.core.connection import get_connection
from database.core.setup import create_tables
from database.repositories.activity import (
    get_recent_activity,
    record_activity,
)
from database.repositories.growth import (
    apply_referral,
    get_growth_profile,
    get_recent_feedback,
    submit_feedback,
)
from database.repositories.admin import (
    get_admin_player_details,
    get_admin_player_overview,
    is_user_suspended,
    set_player_restriction,
    set_user_suspended,
)
from database.repositories.users import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    is_email_verified,
)
from database.repositories.prologue import (
    BACKGROUNDS,
    OPENING_CHOICES,
    choose_background,
    get_or_create_prologue,
    resolve_opening_operation,
    start_opening_operation,
)
from database.repositories.presence import (
    get_online_player_count,
    mark_player_offline,
    mark_player_online,
)
from database.repositories.hospital import (
    get_hospital_patients,
)
from database.repositories.jail import (
    BREAKOUT_NERVE_COST,
    JailInteractionError,
    attempt_jail_break,
    bail_out_inmate,
    calculate_breakout_chance,
    get_jail_inmates,
)

from database.repositories.players import (
    create_player,
    get_player_by_user_id,
    save_player,
)
from database.repositories.pvp import (
    AttackReservationError,
    get_attack_limits,
    get_pvp_targets,
    get_recent_pvp_attacks,
    get_pvp_report,
    get_target_user_id,
    get_unread_pvp_notifications,
    mark_pvp_notifications_read,
    record_pvp_attack,
    release_pvp_attack,
    reserve_pvp_attack,
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
from utils.rate_limit import FixedWindowRateLimiter
from utils.security import (
    hash_password,
    verify_password,
)
from game.housing import get_residence
from game.economy.bank import (
    BankError,
    deposit_cash,
    withdraw_cash,
)
from game.shop import ShopError, get_district_shop, purchase
from game.inventory import (
    INVENTORY_SLOT_CAPACITY,
    ITEMS,
    EquipmentError,
    InventoryError,
    add_item,
    equip_item,
    get_equipment_summary,
    get_item,
    remove_item,
    unequip_item,
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
    SESSION_COOKIE_SECURE=(
        os.environ.get("THE_SMOKE_COOKIE_SECURE", "1")
        == "1"
    ),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_REFRESH_EACH_REQUEST=True,
)

create_tables()

app.jinja_env.globals.update(
    hud_level_xp=xp_required_for_level,
    hud_next_level_xp=lambda level: xp_required_for_level(
        level + 1
    ),
)

rate_limiter = FixedWindowRateLimiter()
SENSITIVE_LIMITS = {
    "/login": (10, 60),
    "/register": (5, 300),
    "/forgot-password": (5, 300),
    "/resend-verification": (3, 300),
}


def configure_logging():
    log_path = os.environ.get("THE_SMOKE_LOG_PATH")

    if not log_path:
        return

    try:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s "
            "%(name)s %(message)s"
        ))
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
    except OSError:
        app.logger.exception(
            "Could not initialise file logging."
        )


configure_logging()


@app.before_request
def enforce_maintenance_and_rate_limits():
    if request.path == "/healthz":
        return None

    if (
        os.environ.get("THE_SMOKE_MAINTENANCE", "0")
        == "1"
        and not request.path.startswith("/static/")
    ):
        return render_template("maintenance.html"), 503

    if (
        not app.config.get("TESTING", False)
        and request.method == "POST"
        and request.path in SENSITIVE_LIMITS
    ):
        limit, window = SENSITIVE_LIMITS[request.path]
        forwarded = request.headers.get(
            "CF-Connecting-IP",
            request.remote_addr or "unknown",
        )
        key = f"{request.path}:{forwarded}"

        if not rate_limiter.allow(
            key,
            limit=limit,
            window_seconds=window,
        ):
            app.logger.warning(
                "rate_limit path=%s ip=%s",
                request.path,
                forwarded,
            )
            return render_template(
                "error.html",
                title="Too many attempts",
                message=(
                    "Please wait a few minutes and "
                    "try again."
                ),
            ), 429

    return None


@app.before_request
def record_authenticated_activity():
    if "user_id" in session:
        mark_player_online(session["user_id"])


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect("/admin/login")

        return view(*args, **kwargs)

    return wrapped


def record_player_action(action_type, summary, metadata=None):
    user_id = session.get("user_id")

    if user_id is None:
        return

    try:
        record_activity(
            user_id,
            action_type,
            summary,
            metadata=metadata,
        )
    except (sqlite3.Error, TypeError):
        app.logger.exception(
            "Could not record player activity."
        )


def percentage(value, maximum):
    if maximum <= 0:
        return 0

    return max(0, min(100, round((value / maximum) * 100)))


@app.route("/healthz")
def healthcheck():
    try:
        connection = get_connection()
        connection.execute("SELECT 1").fetchone()
        connection.close()
    except sqlite3.Error:
        app.logger.exception("Database health check failed.")
        return {"status": "unhealthy"}, 503

    return {"status": "ok"}, 200


@app.errorhandler(500)
def internal_server_error(error):
    app.logger.exception(
        "Unhandled server error path=%s",
        request.path,
        exc_info=error,
    )
    return render_template(
        "error.html",
        title="Something went wrong",
        message=(
            "The Smoke encountered an unexpected error. "
            "Please try again shortly."
        ),
    ), 500


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_authenticated"):
        return redirect("/admin")

    error = None

    if request.method == "POST":
        expected_username = os.environ.get(
            "THE_SMOKE_ADMIN_USERNAME",
            "",
        )
        password_hash = os.environ.get(
            "THE_SMOKE_ADMIN_PASSWORD_HASH",
            "",
        )
        supplied_username = request.form.get(
            "username",
            "",
        )
        supplied_password = request.form.get(
            "password",
            "",
        )

        valid_username = bool(
            expected_username
            and hmac.compare_digest(
                supplied_username,
                expected_username,
            )
        )
        valid_password = False

        if password_hash:
            try:
                valid_password = verify_password(
                    supplied_password,
                    password_hash,
                )
            except ValueError:
                app.logger.error(
                    "Invalid admin password hash."
                )

        if valid_username and valid_password:
            session.clear()
            session["admin_authenticated"] = True
            record_activity(
                None,
                "admin_login",
                "Administrator signed in.",
            )
            return redirect("/admin")

        error = "Invalid administrator credentials."

    return render_template(
        "admin_login.html",
        error=error,
    )


@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template(
        "admin_dashboard.html",
        players=get_admin_player_overview(),
        activities=get_recent_activity(limit=100),
        feedback=get_recent_feedback(limit=100),
    )


@app.route("/admin/users/<int:user_id>")
@admin_required
def admin_user_details(user_id):
    details = get_admin_player_details(user_id)

    if details is None:
        return render_template(
            "error.html",
            title="Player not found",
            message="That player account does not exist.",
        ), 404

    return render_template(
        "admin_player_details.html",
        details=details,
        activities=get_recent_activity(
            user_id=user_id,
            limit=100,
        ),
        item_catalog=ITEMS,
        admin_notice=session.pop(
            "admin_player_notice",
            None,
        ),
    )


@app.route(
    "/admin/users/<int:user_id>/suspension",
    methods=["POST"],
)
@admin_required
def admin_user_suspension(user_id):
    suspended = (
        request.form.get("suspended") == "1"
    )

    if set_user_suspended(user_id, suspended):
        record_activity(
            user_id,
            (
                "admin_suspend"
                if suspended
                else "admin_reactivate"
            ),
            (
                "Account suspended by administrator."
                if suspended
                else "Account reactivated by administrator."
            ),
        )

    return redirect("/admin")


@app.route(
    "/admin/users/<int:user_id>/inventory",
    methods=["POST"],
)
@admin_required
def admin_user_inventory(user_id):
    player_data = get_player_by_user_id(user_id)

    if player_data is None:
        session["admin_player_notice"] = {
            "type": "error",
            "message": "This account has no character.",
        }
        return redirect(f"/admin/users/{user_id}#admin-inventory")

    player = Player(*player_data)
    action = request.form.get("action", "")
    item_key = request.form.get("item_key", "")
    item = get_item(item_key)

    try:
        quantity = int(request.form.get("quantity", "0"))

        if action == "grant":
            result = add_item(player, item_key, quantity)
            verb = "Granted"
            action_type = "admin_item_grant"
        elif action == "remove":
            result = remove_item(player, item_key, quantity)
            verb = "Removed"
            action_type = "admin_item_remove"

            if result.quantity_after == 0 and item is not None:
                equipment = get_equipment_summary(player.id)
                slot = item.equipment_slot
                if slot and equipment.items.get(slot) == item:
                    unequip_item(player.id, slot)
        else:
            raise InventoryError("Choose grant or remove.")

        save_player(player)
        summary = (
            f"{verb} {quantity} × {item.name}. "
            f"Player now owns {result.quantity_after}."
        )
        record_activity(
            user_id,
            action_type,
            summary,
            {
                "item_key": item_key,
                "quantity": quantity,
                "quantity_after": result.quantity_after,
            },
        )
        session["admin_player_notice"] = {
            "type": "success",
            "message": summary,
        }
    except (ValueError, InventoryError) as inventory_error:
        session["admin_player_notice"] = {
            "type": "error",
            "message": (
                "Enter a positive whole-number quantity."
                if isinstance(inventory_error, ValueError)
                else str(inventory_error)
            ),
        }

    return redirect(f"/admin/users/{user_id}#admin-inventory")


@app.route(
    "/admin/users/<int:user_id>/status",
    methods=["POST"],
)
@admin_required
def admin_user_status(user_id):
    restriction = request.form.get(
        "restriction",
        "",
    )
    duration = request.form.get(
        "duration_minutes",
    )
    reason = request.form.get(
        "reason",
        "",
    ).strip()[:200]

    try:
        result = set_player_restriction(
            user_id,
            restriction,
            duration,
        )

        if restriction == "free":
            summary = (
                "Administrator released the player "
                "from Jail/Hospital."
            )
            action_type = "admin_status_release"
        else:
            label = restriction.title()
            summary = (
                f"Administrator sent the player to "
                f"{label} for "
                f"{result['duration_minutes']} minutes."
            )
            if reason:
                summary += f" Reason: {reason}"
            action_type = (
                f"admin_send_to_{restriction}"
            )

        record_activity(
            user_id,
            action_type,
            summary,
            {
                "restriction": restriction,
                "duration_minutes": result[
                    "duration_minutes"
                ],
                "until": result["until"],
                "reason": reason,
            },
        )
        session["admin_player_notice"] = {
            "type": "success",
            "message": summary,
        }
    except ValueError as status_error:
        session["admin_player_notice"] = {
            "type": "error",
            "message": str(status_error),
        }

    return redirect(f"/admin/users/{user_id}")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect("/admin/login")


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect("/login")

    prologue = get_or_create_prologue(session["user_id"])

    if prologue["completed_at"] is None:
        return redirect("/prologue")

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
        prologue=prologue,
    )


@app.route("/operations", methods=["GET", "POST"])
@app.route("/prologue", methods=["GET", "POST"])
def prologue():
    if "user_id" not in session:
        return redirect("/login")

    state = get_or_create_prologue(session["user_id"])
    error = None
    operation_result = None

    if request.method == "POST":
        action = request.form.get("action", "")

        try:
            if action == "choose_background":
                background = request.form.get("background", "")
                choose_background(
                    session["user_id"],
                    background,
                )
                record_player_action(
                    "operation_dossier",
                    (
                        "Selected the "
                        f"{BACKGROUNDS[background]['name']} dossier."
                    ),
                )
            elif action == "start_operation":
                choice = request.form.get("choice", "")
                operation = start_opening_operation(
                    session["user_id"],
                    choice,
                )
                record_player_action(
                    "operation_started",
                    (
                        "Started The Camden Collection "
                        f"using {operation['style'].lower()}."
                    ),
                    {"approach": choice},
                )
            elif action == "resolve_operation":
                operation_result = resolve_opening_operation(
                    session["user_id"]
                )
                record_player_action(
                    "operation_completed",
                    (
                        "Completed The Camden Collection "
                        f"using {operation_result['style'].lower()}."
                    ),
                    {
                        "approach": state[
                            "operation_approach"
                        ],
                    },
                )
            else:
                raise ValueError("Unknown operation action.")
        except ValueError as operation_error:
            error = str(operation_error)

        state = get_or_create_prologue(
            session["user_id"]
        )

    player_data = get_player_by_user_id(
        session["user_id"]
    )
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_player_status(player)
    save_player(player)

    return render_template(
        "prologue.html",
        player=player,
        state=state,
        backgrounds=BACKGROUNDS,
        choices=OPENING_CHOICES,
        error=error,
        mission_result=operation_result,
    )




@app.route("/bank", methods=["GET", "POST"])
def bank():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    save_player(player)
    message = None
    error = None
    block_reason = None

    if player.jail_until is not None:
        block_reason = "Banking is unavailable while you are in jail."
    elif player.hospital_until is not None:
        block_reason = "Banking is unavailable while you are in hospital."
    elif player.travel_destination is not None:
        block_reason = "Banking is unavailable while you are travelling."

    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            if block_reason:
                raise BankError(block_reason)

            amount = int(request.form.get("amount", "0"))
            if action == "deposit":
                transaction = deposit_cash(player, amount)
                verb = "Deposited"
            elif action == "withdraw":
                transaction = withdraw_cash(player, amount)
                verb = "Withdrew"
            else:
                raise BankError("Choose deposit or withdrawal.")

            message = f"{verb} £{transaction.amount:,}."
            record_player_action(
                f"bank_{transaction.transaction_type}",
                message,
                {
                    "amount": transaction.amount,
                    "cash_balance": transaction.cash_balance,
                    "bank_balance": transaction.bank_balance,
                },
            )
        except (ValueError, BankError) as bank_error:
            error = (
                "Enter a positive whole-pound amount."
                if isinstance(bank_error, ValueError)
                else str(bank_error)
            )

    return render_template(
        "bank.html",
        player=player,
        message=message,
        error=error,
        block_reason=block_reason,
    )


@app.route("/shop", methods=["GET", "POST"])
def district_shop():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    save_player(player)
    message = None
    error = None
    shop = get_district_shop(player.current_district)

    if request.method == "POST":
        try:
            quantity = int(request.form.get("quantity", "0"))
            result = purchase(
                session["user_id"],
                player.current_district,
                request.form.get("item_key", ""),
                quantity,
            )
            message = (
                f"Bought {result['quantity']} × "
                f"{result['item'].name} for £{result['total']:,}."
            )
            record_player_action(
                "shop_purchase",
                message,
                {
                    "shop": shop["key"],
                    "item_key": result["item"].item_key,
                    "quantity": result["quantity"],
                    "total": result["total"],
                },
            )
            player_data = get_player_by_user_id(session["user_id"])
            player = Player(*player_data)
        except (ValueError, ShopError) as shop_error:
            error = str(shop_error)

    return render_template(
        "shop.html",
        player=player,
        shop=get_district_shop(player.current_district),
        message=message,
        error=error,
        accessible=(
            player.travel_destination is None
            and player.jail_until is None
            and player.hospital_until is None
        ),
    )

@app.route("/jobs", methods=["GET", "POST"])
def jobs():
    return _work_page("jobs")


@app.route("/inventory", methods=["GET", "POST"])
def inventory():
    return _work_page("inventory")


@app.route("/jobs-inventory", methods=["GET", "POST"])
def jobs_inventory():
    """Keep old bookmarks and cached forms working."""
    active_section = request.form.get("section")
    if active_section is None:
        active_section = request.args.get("section")
    if active_section is None:
        active_section = (
            "inventory"
            if request.form.get("action") == "use_item"
            else "jobs"
        )
    if active_section not in {"jobs", "inventory"}:
        active_section = "jobs"

    if request.method == "GET":
        return redirect(url_for(active_section))

    return _work_page(active_section)


def _work_page(active_section):
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

    allowed_actions = {
        "jobs": {
            "join_career",
            "start_shift",
            "complete_shift",
        },
        "inventory": {"use_item", "equip_item", "unequip_item"},
    }

    if request.method == "POST":
        action = request.form.get("action", "")

        try:
            if action not in allowed_actions[active_section]:
                error = "That action is not available on this page."
            elif action == "join_career":
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
            elif action == "equip_item":
                item = equip_item(
                    player.id,
                    request.form.get("item_key", ""),
                )
                message = (
                    f"{item.name} equipped in your "
                    f"{item.equipment_slot} slot."
                )
            elif action == "unequip_item":
                slot = request.form.get("slot", "")
                unequip_item(player.id, slot)
                message = f"{slot.title()} unequipped."
        except (JobError, InventoryError, EquipmentError) as action_error:
            error = str(action_error)

    save_player(player)

    if request.method == "POST" and message:
        action_prefix = (
            "job" if active_section == "jobs"
            else "inventory"
        )
        record_player_action(
            f"{action_prefix}_"
            f"{request.form.get('action', 'action')}",
            message,
        )

    career = get_career(player.career_key)
    role = get_job_role(player.job_role_key)
    shift_state = get_shift_state(player)
    equipment = get_equipment_summary(getattr(player, "id", 0))
    owned_items = [
        {
            "item": get_item(item_key),
            "quantity": quantity,
            "equipped": (
                get_item(item_key).equipment_slot is not None
                and equipment.items.get(
                    get_item(item_key).equipment_slot
                ) == get_item(item_key)
            ),
            "comparison": (
                (
                    get_item(item_key).strength_bonus
                    if get_item(item_key).category == "weapon"
                    else get_item(item_key).defence_bonus
                )
                - (
                    (
                        equipment.items.get(
                            get_item(item_key).equipment_slot
                        ).strength_bonus
                        if get_item(item_key).category == "weapon"
                        else equipment.items.get(
                            get_item(item_key).equipment_slot
                        ).defence_bonus
                    )
                    if equipment.items.get(
                        get_item(item_key).equipment_slot
                    )
                    else 0
                )
                if get_item(item_key).equipment_slot is not None
                else 0
            ),
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
        equipment=equipment,
        active_section=active_section,
        message=message,
        error=error,
    )


@app.route("/hospital")
def hospital():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(
        session["user_id"]
    )
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_player_status(player)
    save_player(player)

    patients = get_hospital_patients()
    own_patient = next(
        (
            patient
            for patient in patients
            if patient["id"] == player.id
        ),
        None,
    )

    return render_template(
        "hospital.html",
        player=player,
        patients=patients,
        own_patient=own_patient,
    )


@app.route("/jail", methods=["GET", "POST"])
def jail():
    if "user_id" not in session:
        return redirect("/login")

    notice = session.pop("jail_notice", {})
    message = notice.get("message")
    error = notice.get("error")
    interaction_result = None

    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            target_player_id = int(
                request.form.get("target_player_id", "0")
            )
            if action == "pay_bail":
                interaction_result = bail_out_inmate(
                    session["user_id"],
                    target_player_id,
                )
                message = (
                    f"£{interaction_result['cost']:,} bail "
                    f"paid. {interaction_result['target_name']} "
                    "has been released."
                )
                activity_type = "jail_bail_paid"
            elif action == "attempt_breakout":
                interaction_result = attempt_jail_break(
                    session["user_id"],
                    target_player_id,
                )
                if interaction_result["success"]:
                    message = (
                        "Breakout successful. "
                        f"{interaction_result['target_name']} "
                        "is free."
                    )
                elif (
                    interaction_result["consequence"]
                    == "caught"
                ):
                    error = (
                        "Breakout failed. You gained wanted "
                        "level and were jailed for 6 hours."
                    )
                else:
                    error = (
                        "Breakout failed. You gained "
                        f"{BREAKOUT_NERVE_COST - 2} wanted "
                        "level."
                    )
                activity_type = (
                    "jail_breakout_success"
                    if interaction_result["success"]
                    else "jail_breakout_failed"
                )
            else:
                raise JailInteractionError(
                    "Unknown jail action."
                )

            summary = message or error
            record_player_action(
                activity_type,
                summary,
                {
                    "target_player_id": target_player_id,
                    "success": interaction_result["success"],
                },
            )
            if interaction_result["success"]:
                record_activity(
                    interaction_result["target_user_id"],
                    "jail_released_by_player",
                    summary,
                    {
                        "helper_user_id": session["user_id"],
                        "method": interaction_result["action"],
                    },
                )
        except (JailInteractionError, ValueError) as jail_error:
            error = str(jail_error)

        session["jail_notice"] = {
            "message": message,
            "error": error,
        }
        return redirect("/jail")

    player_data = get_player_by_user_id(
        session["user_id"]
    )
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_player_status(player)
    save_player(player)

    inmates = get_jail_inmates()
    helper_stats = {
        "speed": player.speed,
        "dexterity": player.dexterity,
    }
    for inmate in inmates:
        inmate["breakout_chance"] = (
            calculate_breakout_chance(
                helper_stats,
                inmate["level"],
            )
        )

    own_inmate = next(
        (
            inmate
            for inmate in inmates
            if inmate["id"] == player.id
        ),
        None,
    )
    can_help = (
        own_inmate is None
        and player.hospital_until is None
        and player.travel_destination is None
    )

    return render_template(
        "jail.html",
        player=player,
        inmates=inmates,
        own_inmate=own_inmate,
        can_help=can_help,
        breakout_nerve_cost=BREAKOUT_NERVE_COST,
        message=message,
        error=error,
        interaction_result=interaction_result,
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
        recent_activity=get_recent_activity(
            user_id=session["user_id"],
            limit=12,
        ),
        growth=get_growth_profile(session["user_id"]),
        equipment=get_equipment_summary(getattr(player, "id", 0)),
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

    if (
        request.method == "POST"
        and message
        and error is None
    ):
        record_player_action(
            "travel_started",
            message,
            {"destination": destination_key},
        )

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
                active_block = get_training_block(player)
                if active_block is not None:
                    location = (
                        f"in {active_block}"
                        if active_block in {"hospital", "jail"}
                        else active_block
                    )
                    raise GymError(
                        f"You cannot train while {location}."
                    )

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

    if (
        request.method == "POST"
        and message
        and error is None
    ):
        record_player_action(
            f"gym_{request.form.get('action', 'action')}",
            message,
            {
                "gym_key": request.form.get(
                    "gym_key",
                    "",
                ),
                "stat": request.form.get("stat", ""),
            },
        )

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
    work_shift = get_shift_state(player)
    crime_block_reason = None

    if player.jail_until is not None:
        crime_block_reason = (
            "You cannot attempt crimes while in jail."
        )
    elif player.hospital_until is not None:
        crime_block_reason = (
            "You cannot attempt crimes while in hospital."
        )
    elif work_shift is not None:
        crime_block_reason = (
            "You cannot attempt crimes while working a shift. "
            "Finish or collect your shift first."
        )
    elif player.travel_destination is not None:
        crime_block_reason = (
            "You cannot attempt crimes while travelling."
        )

    if request.method == "POST" and crime_block_reason:
        error = crime_block_reason

    elif request.method == "POST":
        crime_key = request.form.get("crime_key", "")
        attempted_crime_key = crime_key
        crime = CRIMES_BY_KEY.get(crime_key)

        if crime is None:
            error = "Crime does not exist."
        else:
            result = commit_crime(player, crime)
            save_player(player)
            record_player_action(
                "crime_attempt",
                (
                    f"Attempted {crime.name}: "
                    f"{'success' if result.success else 'failed'}."
                ),
                {
                    "crime_key": crime.key,
                    "success": result.success,
                    "attempted": result.attempted,
                },
            )

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
        work_shift=work_shift,
        crime_block_reason=crime_block_reason,
    )



@app.route("/fight", methods=["GET", "POST"])
def fight():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    equipment = get_equipment_summary(player.id)
    opponents = get_district_opponents(player.current_district)
    records = get_encounter_records(player.id, opponents)
    result = None
    fought_opponent = None
    error = None

    if request.method == "POST":
        opponent_key = request.form.get("opponent_key", "")
        fought_opponent = OPPONENTS_BY_KEY.get(opponent_key)
        try:
            if fought_opponent is None:
                raise CombatError("Opponent does not exist.")
            record = records.get(fought_opponent.key)
            if record is not None and record.cooldown_seconds > 0:
                raise CombatError(
                    "That opponent is recovering. "
                    f"Try again in {record.cooldown_seconds} seconds."
                )
            result = fight_opponent(
                player,
                equipment,
                fought_opponent,
            )
            record_encounter(
                player.id,
                fought_opponent.key,
                result.victory,
            )
            record_player_action(
                "npc_combat",
                (
                    f"{'Defeated' if result.victory else 'Lost to'} "
                    f"{fought_opponent.name}."
                ),
                {
                    "opponent": fought_opponent.key,
                    "victory": result.victory,
                    "cash_reward": result.cash_reward,
                    "xp_reward": result.xp_reward,
                },
            )
        except CombatError as combat_error:
            error = str(combat_error)

    save_player(player)
    records = get_encounter_records(player.id, opponents)
    return render_template(
        "fight.html",
        player=player,
        opponents=opponents,
        fought_opponent=fought_opponent,
        records=records,
        equipment=equipment,
        energy_cost=COMBAT_ENERGY_COST,
        block_reason=get_combat_block(player),
        result=result,
        error=error,
    )



@app.route("/pvp", methods=["GET", "POST"])
def pvp():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    result = None
    defender = None
    error = None
    selected_approach = request.form.get("approach", "balanced")
    if selected_approach == "balanced":
        selected_approach = "defensive"

    if request.method == "POST":
        try:
            target_id = int(request.form.get("target_id", "0"))
            target_user_id = get_target_user_id(target_id)
            if target_user_id is None:
                raise PvpError("That player does not exist.")
            defender_data = get_player_by_user_id(target_user_id)
            if defender_data is None:
                raise PvpError("That player does not exist.")
            defender = Player(*defender_data)
            update_travel(defender)
            update_player_status(defender)

            limits = reserve_pvp_attack(player.id, defender.id)

            result = fight_player(
                player,
                defender,
                get_equipment_summary(player.id),
                get_equipment_summary(defender.id),
                selected_approach,
                reward_multiplier=limits.reward_multiplier,
            )
            save_player(player)
            save_player(defender)
            attack_id = record_pvp_attack(
                player.id,
                defender.id,
                selected_approach,
                result,
                limits.reward_multiplier,
            )
            record_player_action(
                "pvp_combat",
                (
                    f"{'Defeated' if result.victory else 'Lost to'} "
                    f"{defender.name}."
                ),
                {
                    "defender_id": defender.id,
                    "victory": result.victory,
                    "cash_stolen": result.cash_stolen,
                    "xp_reward": result.xp_reward,
                    "approach": selected_approach,
                },
            )
        except (PvpError, AttackReservationError, ValueError) as pvp_error:
            error = str(pvp_error)
            if defender is not None:
                release_pvp_attack(player.id, defender.id)

    save_player(player)
    targets = get_pvp_targets(player.id, player.current_district)
    for target in targets:
        target_view = SimpleNamespace(
            id=target["id"],
            strength=target["strength"],
            defence=target["defence"],
            speed=target["speed"],
            dexterity=target["dexterity"],
        )
        target["estimate"] = estimate_target(player, target_view)
        target["limits"] = get_attack_limits(player.id, target["id"])

    notifications = get_unread_pvp_notifications(player.id)
    if notifications:
        mark_pvp_notifications_read(player.id)

    return render_template(
        "pvp.html",
        player=player,
        targets=targets,
        approaches=APPROACHES,
        selected_approach=selected_approach,
        energy_cost=PVP_ENERGY_COST,
        block_reason=get_pvp_block(player),
        result=result,
        defender=defender,
        error=error,
        history=get_recent_pvp_attacks(player.id),
        notifications=notifications,
    )


@app.route("/pvp/report/<int:attack_id>")
def pvp_report(attack_id):
    if "user_id" not in session:
        return redirect("/login")
    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")
    player = Player(*player_data)
    report = get_pvp_report(attack_id, player.id)
    if report is None:
        return redirect("/pvp")
    return render_template(
        "pvp_report.html",
        player=player,
        report=report,
    )


@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if "user_id" not in session:
        return redirect("/login")

    error = None
    notice = None
    category = request.form.get("category", "idea")
    message = request.form.get("message", "")

    if request.method == "POST":
        try:
            submit_feedback(
                session["user_id"],
                category,
                message,
                request.form.get("page_path", ""),
            )
            record_player_action(
                "feedback_submitted",
                f"Submitted {category} feedback.",
            )
            notice = (
                "Thank you. Your feedback has been sent "
                "directly to the development dashboard."
            )
            message = ""
        except ValueError as feedback_error:
            error = str(feedback_error)

    return render_template(
        "feedback.html",
        error=error,
        notice=notice,
        category=category,
        message=message,
        page_path=request.args.get(
            "from",
            request.form.get("page_path", ""),
        ),
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect("/")

    error = None
    form_data = {
        "username": "",
        "email": "",
        "invite_code": request.args.get("invite", ""),
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
        form_data["invite_code"] = request.form.get(
            "invite_code",
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
            apply_referral(
                user_id,
                form_data["invite_code"],
            )
            try:
                record_activity(
                    user_id,
                    "account_created",
                    "Player account created.",
                )
            except sqlite3.Error:
                app.logger.exception(
                    "Could not record account creation."
                )
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

        elif is_user_suspended(user[0]):
            error = (
                "This account has been suspended. "
                "Contact support if you believe this is an error."
            )

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
            session.permanent = True
            record_player_action(
                "login",
                "Player signed in.",
            )
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


