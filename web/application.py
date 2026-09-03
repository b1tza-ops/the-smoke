import hmac
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import SimpleNamespace
from game.world.city import directory as city_directory
from game.economy.loans import (
    DAILY_INTEREST_RATE as LOAN_DAILY_RATE,
    MINIMUM_LEVEL as LOAN_MINIMUM_LEVEL,
    MINIMUM_LOAN as LOAN_MINIMUM,
    LoanError,
)
from database.repositories.loans import (
    LOAN_DISTRICT,
    borrow as borrow_from_shark,
    collect_if_overdue as collect_overdue_loan,
    get_loan as get_loan_state,
    recent_transactions as loan_transactions,
    repay as repay_shark,
)
from game.handbook import (
    CLOSING as HANDBOOK_CLOSING,
    GUIDES as HANDBOOK_GUIDES,
    INTRO as HANDBOOK_INTRO,
    RULES as HANDBOOK_RULES,
    get_guide,
    inline as handbook_inline,
    sections as handbook_sections,
)
from game.casino import (
    MINIMUM_BET as CASINO_MINIMUM_BET,
    MINIMUM_LEVEL as CASINO_MINIMUM_LEVEL,
    CasinoError,
    maximum_bet as casino_maximum_bet,
)
from game.casino.limits import denominations as casino_denominations
from game.casino.blackjack import (
    OUTCOME_LINES as BLACKJACK_OUTCOME_LINES,
    BlackjackError,
    available_actions as blackjack_actions,
    describe as describe_table,
    hand_value as blackjack_hand_value,
)
from game.casino.keno import (
    MAXIMUM_ROUNDS as KENO_MAXIMUM_ROUNDS,
    MAXIMUM_SPOTS as KENO_MAXIMUM_SPOTS,
    MINIMUM_SPOTS as KENO_MINIMUM_SPOTS,
    PAYTABLE as KENO_PAYTABLE,
    POOL_SIZE as KENO_POOL_SIZE,
    KenoError,
)
from game.casino.slots import (
    PAIR as SLOTS_PAIR,
    SYMBOL_NAMES as SLOTS_SYMBOL_NAMES,
    THREE_OF_A_KIND as SLOTS_THREE_OF_A_KIND,
)
from database.repositories.casino import (
    act_on_table,
    deal_blackjack,
    get_open_table,
    play_keno,
    play_slots,
    recent_rounds as recent_casino_rounds,
)
from game.world.districts import (
    DISTRICTS,
    DISTRICTS_BY_KEY,
    get_district,
    get_travel_route,
)
from game.world.transport import DEFAULT_TRANSPORT_KEY, available_modes
from game.world.travel import (
    TravelError,
    get_active_travel,
    start_travel,
    update_travel,
)
from game.crime.tools import tools_for
from game.crime import (
    CRIMES,
    CRIMES_BY_KEY,
    commit_crime,
    crime_progression_for,
)
from game.combat.rating import matchmaking_label
from game.combat.streaks import get_streak_progress
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
    GAIN_BAR_SEGMENTS,
    GAIN_SCALE_MAX,
    GymError,
    UnknownGymError,
    VALID_BATTLE_STATS,
    calculate_training_gain,
    happiness_cost,
    get_district_gyms,
    get_gym,
    get_training_block,
    get_unlocked_gyms,
    select_gym,
    train,
    unlock_gym,
)
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    redirect,
    session,
    url_for,
)
from markupsafe import escape
from database.core.connection import get_connection
from database.core.setup import create_tables
from database.repositories.activity import (
    get_recent_activity,
    record_activity,
)
from database.repositories.site_controls import (
    DEFAULT_MESSAGE as DEFAULT_MAINTENANCE_MESSAGE,
    DEFAULT_TITLE as DEFAULT_MAINTENANCE_TITLE,
    get_operations_settings,
    update_operations_settings,
)
from database.repositories.growth import (
    apply_referral,
    get_growth_profile,
    get_recent_feedback,
    submit_feedback,
)
from database.repositories.moderation import get_user_role
from database.repositories.admin import (
    get_admin_metrics,
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
from database.repositories.fence import FenceError, sell_to_fence
from database.repositories.market import (
    MarketError,
    buy_listing,
    cancel_listing,
    create_listing,
    get_open_listings,
)
from database.repositories.operations import (
    get_campaign,
    resolve_operation,
    start_operation,
)
from database.repositories.prologue import (
    BACKGROUNDS,
    choose_background,
    get_or_create_prologue,
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
from database.repositories.pvp_contracts import (
    ContractClaimError,
    claim_contract,
    get_contract_board,
    record_contract_fight,
)
from game.combat.pvp import PVP_HOSPITAL_SECONDS
from game.player.progression import award_xp
from game.player.status import send_to_hospital
from game.combat.turns import MAXIMUM_TURNS, TurnError
from database.repositories.safe import (
    burgle,
    deposit as safe_deposit,
    safe_for,
    withdraw as safe_withdraw,
)
from game.crime.burglary import (
    BURGLARY_NERVE_COST,
    BurglaryError,
    odds_against,
)
from game.housing.safe import SafeError
from database.repositories.fights import (
    flee as flee_fight,
    get_open_fight,
    start_fight,
    take_fight_turn,
    weapons_for,
)
from database.repositories.vehicles import (
    active_vehicle,
    buy_vehicle,
    garage_for,
    sell_vehicle,
    set_active,
)
from game.vehicles.definitions import VEHICLES, get_vehicle
from game.vehicles.service import (
    DRIVE_KEY,
    PULLED_OVER_SECONDS,
    VehicleError,
    driving_mode,
    resale_value,
    stop_chance,
)
from database.repositories.bounties import (
    bounties_posted_by,
    find_target,
    get_board,
    open_bounty_totals,
    post_bounty,
    sweep,
    total_open,
)
from game.combat.bounties import (
    BOUNTY_FEE_PERCENT,
    BOUNTY_LIFETIME_DAYS,
    BOUNTY_MAXIMUM,
    BOUNTY_MINIMUM,
    BountyError,
    posting_fee,
    total_cost,
)
from database.repositories.pvp import (
    get_pending_aftermath,
    settle_aftermath,
    AttackReservationError,
    get_attack_limits,
    get_pvp_targets,
    get_recent_pvp_attacks,
    get_pvp_report,
    get_pvp_profile,
    get_pvp_leaderboard,
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
from auth.moderation import (
    MODERATOR_ROLES,
    ModerationError,
    ROLES,
    ban_user,
    get_history,
    is_account_blocked,
    reverse_moderation,
    set_user_role,
    suspend_user,
    warn_user,
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
from utils.images import is_renderable_image
from utils.security import (
    hash_password,
    verify_password,
)
from game.housing import (
    FACILITIES,
    RESIDENCES,
    HousingError,
    comfort_for,
    get_residence,
    gym_gain_bonus,
    recovery_bonus,
)
from database.repositories.housing import (
    facilities_for,
    install_facility,
    move_house,
    pay_upkeep,
    upkeep_for,
)
from game.economy.bank import (
    BankError,
    deposit_cash,
    withdraw_cash,
)
from game.economy.market import COMMISSION_RATE, minimum_price
from game.economy.fence import (
    FENCE_RATE,
    SPECIALITY_RATE,
    fence_price,
    get_fence,
)
from game.shop import (
    ShopError,
    get_district_shop,
    get_venue,
    purchase,
    purchase_at,
)
from game.inventory import (
    AMMO_KEYS,
    INVENTORY_SLOT_CAPACITY,
    ITEMS,
    ITEMS_BY_KEY,
    EquipmentError,
    InventoryError,
    add_item,
    equip_item,
    get_equipment,
    get_equipment_summary,
    get_item,
    loaded_rounds,
    remove_item,
    spend_ammo,
    unequip_item,
    use_item,
)
from game.jobs import (
    CAREERS,
    JobError,
    cancel_shift,
    complete_shift,
    get_career,
    get_job_role,
    get_shift_state,
    join_career,
    start_shift,
)
from game.operations import (
    COMPLETED as OPERATION_COMPLETED,
    approach_shortfalls,
)
from game.player import Player
from game.player.happiness import crime_success_penalty
from game.player.progression import xp_required_for_level
from game.player.regeneration import player_regeneration_forecast
from game.player.status import update_player_status


def _session_secret():
    """The key that signs session cookies.

    Falling back to a random key is right for development and wrong
    everywhere else: each Gunicorn worker would generate a different
    one, so a player's session would work or not depending on which
    worker answered, and every restart would sign everybody out. That
    reads as a flaky site rather than as the misconfiguration it is.

    So it is only a fallback when nothing is at stake.
    """
    configured = os.environ.get("THE_SMOKE_SECRET_KEY")

    if configured:
        return configured

    if os.environ.get("THE_SMOKE_ENVIRONMENT") == "production":
        raise RuntimeError(
            "THE_SMOKE_SECRET_KEY must be set in production; refusing "
            "to start with a per-worker random key."
        )

    return secrets.token_hex(32)


app = Flask(__name__)

app.config.update(
    SECRET_KEY=_session_secret(),
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


def hud_duration(seconds):
    """A countdown the HUD can show without a unit legend.

    Mirrored by the tooltip script so the server-rendered value and the
    one it ticks down to look the same.
    """
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m"

    if minutes:
        return f"{minutes}m {remaining_seconds:02d}s"

    return f"{remaining_seconds}s"


def percentage(value, maximum):
    """A meter width, clamped to something a bar can actually draw.

    The clamp is the point. The HUD used to work each of its five
    meters out inline in the template with no bounds, so a player whose
    XP sat below their level's floor rendered `--progress:-950%` on
    every page in the game. Routes had this helper all along; the
    template just did not use it.
    """
    if maximum <= 0:
        return 0

    return max(0, min(100, round((value / maximum) * 100)))


app.jinja_env.globals.update(
    hud_percent=percentage,
    hud_level_xp=xp_required_for_level,
    hud_next_level_xp=lambda level: xp_required_for_level(
        level + 1
    ),
    hud_forecast=player_regeneration_forecast,
    hud_duration=hud_duration,
    operation_shortfalls=approach_shortfalls,
)

rate_limiter = FixedWindowRateLimiter()
# A real bcrypt hash of a value nobody can supply, compared against
# when the username does not exist so that a failed sign-in costs the
# same either way. Generated once at import; the password it encodes is
# random and immediately discarded.
ABSENT_USER_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


SENSITIVE_LIMITS = {
    "/login": (10, 60),
    "/register": (5, 300),
    "/forgot-password": (5, 300),
    "/resend-verification": (3, 300),
    # Staff sign-in was the only login in the building with no limit on
    # it, which made the most valuable password on the site the easiest
    # one to grind. Tighter than the player limit because nobody signs
    # in here often and a wrong guess is far more interesting.
    "/admin/login": (5, 900),
}



@app.after_request
def set_security_headers(response):
    """Headers the app should send on every response.

    Cloudflare may add some of these, but the origin should not depend
    on a proxy for them -- anything that reaches the app directly, or a
    future move off Cloudflare, would quietly lose them.

    The CSP allows inline scripts and styles because this project uses
    both throughout (the casino animations, the fight playback, every
    page's `style` attribute). Tightening that means nonces on roughly
    eighteen inline blocks, which is worth doing and is not a one-line
    change; `frame-ancestors` and the rest still hold today.
    """
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data:; "
        "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com; "
        "style-src 'self' 'unsafe-inline'; "
        "frame-src https://challenges.cloudflare.com; "
        "form-action 'self'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'",
    )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Referrer-Policy", "strict-origin-when-cross-origin"
    )
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )

    if request.is_secure:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )

    return response


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

    public_request = not (
        request.path.startswith("/static/")
        or request.path.startswith("/admin")
    )
    if public_request:
        settings = get_operations_settings()
        environment_override = (
            os.environ.get("THE_SMOKE_MAINTENANCE", "0") == "1"
        )
        if environment_override or settings.maintenance_active():
            return render_template(
                "maintenance.html",
                maintenance_title=(
                    settings.maintenance_title
                    if not environment_override
                    else DEFAULT_MAINTENANCE_TITLE
                ),
                maintenance_message=(
                    settings.maintenance_message
                    if not environment_override
                    else DEFAULT_MAINTENANCE_MESSAGE
                ),
                maintenance_ends_at=(
                    settings.maintenance_ends_at
                    if not environment_override
                    else None
                ),
            ), 503

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


@app.context_processor
def inject_operations_announcement():
    try:
        settings = get_operations_settings()
    except sqlite3.Error:
        return {"site_announcement": None}
    return {
        "site_announcement": (
            settings.announcement_message
            if settings.announcement_enabled
            and settings.announcement_message.strip()
            else None
        ),
    }


@app.before_request
def record_authenticated_activity():
    if "user_id" in session:
        mark_player_online(session["user_id"])


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect("/admin/login")

        if "admin_role" not in session:
            # A session opened before staff sign-in existed carries no
            # role or actor, so there is nothing to attribute an
            # audited action to. Make it sign in again rather than
            # guessing who is holding it.
            session.clear()
            return redirect("/admin/login")

        return view(*args, **kwargs)

    return wrapped


def admin_role_required(view):
    """Restrict a panel action to full administrators.

    Moderators can reach the panel but only to use the moderation
    controls; the older operational tools (granting items, forcing
    jail/hospital) stay with administrators and the server operator.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect("/admin/login")

        if "admin_role" not in session:
            session.clear()
            return redirect("/admin/login")

        if session.get("admin_role") != "admin":
            session["admin_player_notice"] = {
                "type": "error",
                "message": (
                    "That action requires an administrator."
                ),
            }
            user_id = kwargs.get("user_id")
            return redirect(
                f"/admin/users/{user_id}"
                if user_id is not None
                else "/admin"
            )

        return view(*args, **kwargs)

    return wrapped


def current_admin_actor():
    """Return the acting account id, or None for the server operator."""
    return session.get("admin_user_id")


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


def build_weapon_column(player_id, equipment):
    """The loadout as the attack screen draws it, down the left.

    One tile per firearm slot plus fists, which are always there and
    never run out. A slot with nothing in it still gets a tile -- the
    gap is information, the same way Torn shows an empty throwable
    slot.

    Ammunition is counted per calibre, so two pistols sharing a calibre
    correctly show the same pool rather than implying two of them.
    """
    rounds = loaded_rounds(player_id)
    unloaded = set(getattr(equipment, "unloaded", ()) or ())
    column = []

    for slot in ("primary", "secondary"):
        item = equipment.items.get(slot) if equipment else None
        if item is None:
            column.append({
                "slot": slot,
                "name": None,
                "empty": True,
            })
            continue

        ammo_key = getattr(item, "ammo_key", None)
        column.append({
            "slot": slot,
            "name": item.name,
            "key": item.key,
            "empty": False,
            "ammo_key": ammo_key,
            "rounds": rounds.get(ammo_key, 0) if ammo_key else None,
            "unloaded": item.key in unloaded,
        })

    column.append({
        "slot": "fists",
        "name": "Fists",
        "key": "fists",
        "empty": False,
        "ammo_key": None,
        "rounds": None,
        "unloaded": False,
    })

    return column


def build_pvp_playback(result):
    """Shape a finished fight for the arena's round-by-round replay.

    Rounds record raw health, and maximum health grows with level, so
    the client is given each fighter's scale rather than assuming 100.
    """
    if result is None:
        return None

    return {
        "victory": result.victory,
        "total_rounds": max(
            (event.round_number for event in result.rounds),
            default=1,
        ),
        "max_health": {
            "attacker": result.attacker_max_health,
            "defender": result.defender_max_health,
        },
        "start_health": {
            "attacker": result.attacker_start_health,
            "defender": result.defender_start_health,
        },
        "rounds": [
            {
                "round": event.round_number,
                "actor": event.actor,
                "event": event.event,
                "damage": event.damage,
                "attacker": event.attacker_health,
                "defender": event.defender_health,
            }
            for event in result.rounds
        ],
    }


def _authenticate_staff_account(username, password):
    """Authenticate a moderator or administrator by game account.

    Returns None for any failure -- unknown account, wrong password,
    insufficient role, or a suspended/banned account -- so the caller
    shows one generic error and never reveals which check failed.
    """
    if not username or not password:
        return None

    user = get_user_by_username(username)

    if user is None:
        return None

    try:
        if not verify_password(password, user[3]):
            return None
    except ValueError:
        return None

    role = get_user_role(user[0])

    if role not in MODERATOR_ROLES:
        return None

    if is_user_suspended(user[0]) or is_account_blocked(user[0]):
        return None

    return {
        "user_id": user[0],
        "username": user[1],
        "role": role,
    }


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
            session["admin_user_id"] = None
            session["admin_role"] = "admin"
            session["admin_display_name"] = "Server operator"
            record_activity(
                None,
                "admin_login",
                "Server operator signed in.",
            )
            return redirect("/admin")

        staff = _authenticate_staff_account(
            supplied_username,
            supplied_password,
        )

        if staff is not None:
            session.clear()
            session["admin_authenticated"] = True
            session["admin_user_id"] = staff["user_id"]
            session["admin_role"] = staff["role"]
            session["admin_display_name"] = staff["username"]
            record_activity(
                staff["user_id"],
                "admin_login",
                f"{staff['role'].title()} signed in to operations.",
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
    operations = get_operations_settings()
    player_search = request.args.get("q", "").strip()[:100]
    player_status = request.args.get("status", "all")
    return render_template(
        "admin_dashboard.html",
        players=get_admin_player_overview(
            search=player_search,
            status=player_status,
        ),
        metrics=get_admin_metrics(),
        player_search=player_search,
        player_status=player_status,
        activities=get_recent_activity(limit=100),
        feedback=get_recent_feedback(limit=100),
        admin_role=session.get("admin_role"),
        admin_display_name=session.get(
            "admin_display_name",
            "Operations",
        ),
        operations=operations,
        operations_notice=session.pop("operations_notice", None),
    )


@app.route("/admin/maintenance-preview")
@admin_required
def maintenance_preview():
    settings = get_operations_settings()
    return render_template(
        "maintenance.html",
        maintenance_title=settings.maintenance_title,
        maintenance_message=settings.maintenance_message,
        maintenance_ends_at=settings.maintenance_ends_at,
    )


def _admin_utc_datetime(raw_value):
    if not raw_value:
        return None
    parsed = datetime.fromisoformat(raw_value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@app.route("/admin/operations", methods=["POST"])
@admin_role_required
def admin_operations():
    current = get_operations_settings()
    action = request.form.get("action", "save")

    if action == "cancel_maintenance":
        update_operations_settings(
            maintenance_enabled=False,
            maintenance_starts_at=None,
            maintenance_ends_at=None,
            maintenance_title=current.maintenance_title,
            maintenance_message=current.maintenance_message,
            registration_open=current.registration_open,
            announcement_enabled=current.announcement_enabled,
            announcement_message=current.announcement_message,
        )
        record_activity(
            current_admin_actor(),
            "operations_update",
            "Scheduled maintenance cancelled.",
        )
        session["operations_notice"] = "Maintenance schedule cancelled."
        return redirect("/admin#operations-controls")

    try:
        enabled = request.form.get("maintenance_enabled") == "1"
        starts = _admin_utc_datetime(
            request.form.get("maintenance_starts_at", "")
        )
        ends = _admin_utc_datetime(
            request.form.get("maintenance_ends_at", "")
        )
        title = request.form.get("maintenance_title", "").strip()
        message = request.form.get("maintenance_message", "").strip()
        announcement = request.form.get(
            "announcement_message", ""
        ).strip()

        if enabled and (starts is None or ends is None):
            raise ValueError("Choose both a maintenance start and end time.")
        if enabled and ends <= starts:
            raise ValueError("Maintenance must end after it starts.")
        if enabled and not title:
            raise ValueError("Add a maintenance page title.")
        if enabled and not message:
            raise ValueError("Add a maintenance page message.")
        if len(title) > 80 or len(message) > 600 or len(announcement) > 240:
            raise ValueError("One of the messages is too long.")

        update_operations_settings(
            maintenance_enabled=enabled,
            maintenance_starts_at=(starts.isoformat() if starts else None),
            maintenance_ends_at=(ends.isoformat() if ends else None),
            maintenance_title=title or DEFAULT_MAINTENANCE_TITLE,
            maintenance_message=message or DEFAULT_MAINTENANCE_MESSAGE,
            registration_open=(
                request.form.get("registration_open") == "1"
            ),
            announcement_enabled=(
                request.form.get("announcement_enabled") == "1"
            ),
            announcement_message=announcement,
        )
    except (TypeError, ValueError) as error:
        session["operations_notice"] = str(error)
        return redirect("/admin#operations-controls")

    record_activity(
        current_admin_actor(),
        "operations_update",
        "Global game controls updated.",
        metadata={
            "maintenance_enabled": enabled,
            "registration_open": request.form.get("registration_open") == "1",
            "announcement_enabled": request.form.get("announcement_enabled") == "1",
        },
    )
    session["operations_notice"] = "Operations settings saved."
    return redirect("/admin#operations-controls")


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
        moderation_history=get_history(user_id),
        assignable_roles=ROLES,
        admin_role=session.get("admin_role"),
        admin_user_id=session.get("admin_user_id"),
    )


@app.route(
    "/admin/users/<int:user_id>/suspension",
    methods=["POST"],
)
@admin_role_required
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
@admin_role_required
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
@admin_role_required
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


@app.route(
    "/admin/users/<int:user_id>/moderation",
    methods=["POST"],
)
@admin_required
def admin_user_moderation(user_id):
    action = request.form.get("action", "")
    reason = request.form.get("reason", "").strip()[:200]
    actor_id = current_admin_actor()

    try:
        if action == "warn":
            warn_user(actor_id, user_id, reason)
            summary = f"Warning issued. Reason: {reason}"

        elif action == "suspend":
            raw_duration = request.form.get(
                "duration_minutes",
                "",
            ).strip()

            if raw_duration:
                if not raw_duration.isdigit():
                    raise ModerationError(
                        "Enter a positive whole number of minutes, "
                        "or leave the duration blank to suspend "
                        "indefinitely."
                    )
                duration = int(raw_duration)
            else:
                duration = None

            until = suspend_user(
                actor_id,
                user_id,
                reason,
                duration_minutes=duration,
            )
            summary = (
                f"Account suspended until {until}. "
                f"Reason: {reason}"
                if until
                else
                f"Account suspended indefinitely. "
                f"Reason: {reason}"
            )

        elif action == "ban":
            ban_user(actor_id, user_id, reason)
            summary = f"Account banned. Reason: {reason}"

        elif action == "reverse":
            reverse_moderation(actor_id, user_id, reason)
            summary = (
                f"Account restored to active. Reason: {reason}"
            )

        else:
            raise ModerationError(
                "Choose warn, suspend, ban or restore."
            )

        record_activity(
            user_id,
            f"moderation_{action}",
            summary,
            {
                "actor_user_id": actor_id,
                "reason": reason,
            },
        )
        session["admin_player_notice"] = {
            "type": "success",
            "message": summary,
        }
    except (ValueError, ModerationError) as moderation_error:
        session["admin_player_notice"] = {
            "type": "error",
            "message": str(moderation_error),
        }

    return redirect(
        f"/admin/users/{user_id}#admin-moderation"
    )


@app.route(
    "/admin/users/<int:user_id>/role",
    methods=["POST"],
)
@admin_role_required
def admin_user_role(user_id):
    new_role = request.form.get("role", "")
    actor_id = current_admin_actor()

    try:
        set_user_role(actor_id, user_id, new_role)
        summary = f"Role set to {new_role}."
        record_activity(
            user_id,
            "moderation_role_change",
            summary,
            {
                "actor_user_id": actor_id,
                "role": new_role,
            },
        )
        session["admin_player_notice"] = {
            "type": "success",
            "message": summary,
        }
    except ModerationError as role_error:
        session["admin_player_notice"] = {
            "type": "error",
            "message": str(role_error),
        }

    return redirect(
        f"/admin/users/{user_id}#admin-moderation"
    )


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect("/admin/login")


@app.route("/")
def home():
    if "user_id" not in session:
        # A public landing page rather than a bounce to /login.
        #
        # This used to 302 straight to the login form, which meant the
        # one URL people search for and link to -- the bare domain --
        # had no content of its own. A crawler arriving here found a
        # password field and nothing describing what the site is, and a
        # curious visitor found the same.
        return render_template(
            "landing.html",
            guides=HANDBOOK_GUIDES,
        )

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
        "health_percent": percentage(player.health, player.max_health),
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
                operation_key = request.form.get("operation", "")
                choice = request.form.get("choice", "")
                operation, approach = start_operation(
                    session["user_id"],
                    operation_key,
                    choice,
                )
                record_player_action(
                    "operation_started",
                    (
                        f"Started {operation.name} "
                        f"using {approach.style.lower()}."
                    ),
                    {
                        "operation": operation_key,
                        "approach": choice,
                    },
                )
            elif action == "resolve_operation":
                operation_key = request.form.get("operation", "")
                operation, approach, paydown = resolve_operation(
                    session["user_id"],
                    operation_key,
                )
                operation_result = {
                    "operation": operation,
                    "approach": approach,
                    "paydown": paydown,
                }
                record_player_action(
                    "operation_completed",
                    (
                        f"Completed {operation.name} "
                        f"using {approach.style.lower()}."
                    ),
                    {
                        "operation": operation_key,
                        "approach": approach.key,
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

    campaign = get_campaign(session["user_id"])

    return render_template(
        "prologue.html",
        player=player,
        state=state,
        backgrounds=BACKGROUNDS,
        campaign=campaign,
        completed_count=sum(
            1
            for status in campaign
            if status.stage == OPERATION_COMPLETED
        ),
        error=error,
        operation_result=operation_result,
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

CASINO_DISTRICT = "soho"

CASINO_TABLES = (
    {
        "key": "slots",
        "endpoint": "casino_slots",
        "name": "Fruit Machines",
        "blurb": "Three reels, one payline. The quickest way to find out.",
        "edge": "8.3% house edge",
    },
    {
        "key": "keno",
        "endpoint": "casino_keno",
        "name": "Keno",
        "blurb": "Mark your card. The house draws twenty.",
        "edge": "8–10% house edge",
    },
    {
        "key": "blackjack",
        "endpoint": "casino_blackjack",
        "name": "Blackjack",
        "blurb": "Six decks, 3:2, splits and surrender. Beat the dealer.",
        "edge": "0.2% house edge",
    },
)


def _casino_player():
    """Load the player, or None when there is no session to speak of."""
    if "user_id" not in session:
        return None
    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return None
    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    save_player(player)
    return player


def _casino_shell(player):
    """Everything every casino page needs."""
    return {
        "player": player,
        "tables": CASINO_TABLES,
        "minimum_bet": CASINO_MINIMUM_BET,
        "maximum_bet": casino_maximum_bet(player.level),
        "minimum_level": CASINO_MINIMUM_LEVEL,
        "denominations": casino_denominations(player.level),
        "accessible": (
            player.level >= CASINO_MINIMUM_LEVEL
            and player.current_district == CASINO_DISTRICT
            and player.travel_destination is None
            and player.jail_until is None
            and player.hospital_until is None
        ),
    }


def _read_bet(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise CasinoError("Choose a stake.")


def _wants_json():
    """True when the page is playing a round without reloading itself."""
    return request.headers.get("X-Requested-With") == "casino"


def _casino_state(player, payout=0, message=None, error=None):
    """The bits of a round the page needs to update in place."""
    return {
        "ok": error is None,
        "error": error,
        "message": message,
        "payout": payout,
        "money": player.money,
        "maximum_bet": casino_maximum_bet(player.level),
    }


def _casino_message(line, staked, payout):
    net = payout - staked
    if net > 0:
        return f"{line}. You win £{net:,}."
    if net == 0:
        return f"{line}. Stake returned."
    return f"{line}. You lose £{-net:,}."


@app.route("/casino")
def casino():
    player = _casino_player()
    if player is None:
        return redirect("/login")
    return render_template(
        "casino.html",
        history=recent_casino_rounds(session["user_id"]),
        open_table=get_open_table(session["user_id"]),
        **_casino_shell(player),
    )


@app.route("/casino/slots", methods=["GET", "POST"])
def casino_slots():
    player = _casino_player()
    if player is None:
        return redirect("/login")

    message = error = spin = None
    payout = 0

    if request.method == "POST":
        try:
            bet = _read_bet(request.form.get("bet"))
            spin, payout = play_slots(session["user_id"], bet)
            message = _casino_message(spin.line, bet, payout)
            record_player_action("casino_round", message, {"game": "slots"})
            player = Player(*get_player_by_user_id(session["user_id"]))
        except CasinoError as casino_error:
            error = str(casino_error)

        if _wants_json():
            return jsonify({
                **_casino_state(player, payout, message, error),
                "reels": list(spin.reels) if spin else [],
                "line": spin.line if spin else "",
                "names": SLOTS_SYMBOL_NAMES,
            })

    return render_template(
        "casino_slots.html",
        message=message,
        error=error,
        spin=spin,
        payout=payout,
        paytable=SLOTS_THREE_OF_A_KIND,
        pairs=SLOTS_PAIR,
        names=SLOTS_SYMBOL_NAMES,
        **_casino_shell(player),
    )


@app.route("/casino/keno", methods=["GET", "POST"])
def casino_keno():
    player = _casino_player()
    if player is None:
        return redirect("/login")

    message = error = None
    cards = ()
    payout = 0
    staked = 0
    picks = []

    if request.method == "POST":
        picks = request.form.getlist("picks")
        try:
            bet = _read_bet(request.form.get("bet"))
            rounds = _read_bet(request.form.get("rounds") or "1")
            cards, payout = play_keno(
                session["user_id"], bet, picks, rounds
            )
            staked = bet * len(cards)
            hits = sum(len(card.hits) for card in cards)
            line = (
                f"{hits} matched across {len(cards)} rounds"
                if len(cards) > 1 else cards[0].line
            )
            message = _casino_message(line, staked, payout)
            record_player_action("casino_round", message, {"game": "keno"})
            player = Player(*get_player_by_user_id(session["user_id"]))
        except (CasinoError, KenoError) as casino_error:
            error = str(casino_error)

        if _wants_json():
            return jsonify({
                **_casino_state(player, payout, message, error),
                "staked": staked,
                "rounds": [
                    {
                        "drawn": sorted(card.drawn),
                        "hits": list(card.hits),
                        "line": card.line,
                        "payout": card.payout,
                    }
                    for card in cards
                ],
            })

    return render_template(
        "casino_keno.html",
        message=message,
        error=error,
        cards=cards,
        payout=payout,
        staked=staked,
        picks=[int(pick) for pick in picks if str(pick).isdigit()],
        paytable=KENO_PAYTABLE,
        pool=KENO_POOL_SIZE,
        minimum_spots=KENO_MINIMUM_SPOTS,
        maximum_spots=KENO_MAXIMUM_SPOTS,
        maximum_rounds=KENO_MAXIMUM_ROUNDS,
        **_casino_shell(player),
    )


@app.route("/casino/blackjack", methods=["GET", "POST"])
def casino_blackjack():
    player = _casino_player()
    if player is None:
        return redirect("/login")

    message = error = None
    payout = 0
    finished = None

    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            if action == "deal":
                bet = _read_bet(request.form.get("bet"))
                state, paid = deal_blackjack(session["user_id"], bet)
            else:
                state, paid = act_on_table(session["user_id"], action)

            if paid is not None:
                finished = state
                payout = paid
                message = _casino_message(
                    describe_table(state), state.staked, paid
                )
                record_player_action(
                    "casino_round", message, {"game": "blackjack"}
                )
            player = Player(*get_player_by_user_id(session["user_id"]))
        except (CasinoError, BlackjackError) as casino_error:
            error = str(casino_error)

    table = get_open_table(session["user_id"])
    return render_template(
        "casino_blackjack.html",
        message=message,
        error=error,
        table=table,
        finished=finished,
        payout=payout,
        actions=blackjack_actions(table) if table else (),
        hand_value=blackjack_hand_value,
        outcome_lines=BLACKJACK_OUTCOME_LINES,
        **_casino_shell(player),
    )


def _optional_player():
    """The signed-in player, or None.

    The handbook is readable logged out: someone deciding whether to
    play should be able to read the rules and the guides first.
    """
    if "user_id" not in session:
        return None
    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return None
    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    save_player(player)
    return player


@app.before_request
def _collect_overdue_loan():
    """Ronnie's people catch up with you wherever you are.

    Run per request rather than on the loan page, so a debt cannot be
    dodged by never visiting him. A failure here must never take a page
    down with it -- the worst case is that a collection waits for the
    next request.
    """
    if "user_id" not in session or request.endpoint == "static":
        return
    try:
        collect_overdue_loan(session["user_id"])
    except sqlite3.Error:
        pass


# Ronnie's portrait is dropped in as a file rather than declared, so the
# page falls back to his initials until the artwork exists. Resolved once
# at import: a stat per request would buy nothing.
LOAN_SHARK_PORTRAIT = "npc/ronnie-dell.webp"
_LOAN_SHARK_PORTRAIT = (
    LOAN_SHARK_PORTRAIT
    if (Path(app.static_folder) / LOAN_SHARK_PORTRAIT).exists()
    else None
)


def _read_loan_amount(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise LoanError("Write a figure Ronnie can read.")


@app.route("/loanshark", methods=["GET", "POST"])
def loan_shark():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    save_player(player)

    message = error = None

    if request.method == "POST":
        try:
            amount = _read_loan_amount(
                request.form.get("amount")
            )
            if request.form.get("action") == "borrow":
                taken, principal = borrow_from_shark(session["user_id"], amount)
                message = (
                    f"Ronnie counts out £{taken:,}. You now owe "
                    f"£{principal:,} on the principal."
                )
            else:
                paid, after = repay_shark(session["user_id"], amount)
                message = (
                    f"You hand over £{paid:,}. "
                    + (
                        "Ronnie tears the page out of the book."
                        if after.settled
                        else f"£{after.balance:,} still on the book."
                    )
                )
            record_player_action("loan_shark", message, {})
            player = Player(*get_player_by_user_id(session["user_id"]))
        except LoanError as loan_error:
            error = str(loan_error)

    state = get_loan_state(session["user_id"]) or {}
    return render_template(
        "loanshark.html",
        player=player,
        portrait=_LOAN_SHARK_PORTRAIT,
        message=message,
        error=error,
        loan=state.get("loan"),
        due_at=state.get("due_at"),
        overdue=state.get("overdue", False),
        maximum=state.get("maximum", 0),
        headroom=state.get("headroom", 0),
        minimum_loan=LOAN_MINIMUM,
        minimum_level=LOAN_MINIMUM_LEVEL,
        daily_rate=LOAN_DAILY_RATE,
        history=loan_transactions(session["user_id"]),
        accessible=(
            player.level >= LOAN_MINIMUM_LEVEL
            and player.current_district == LOAN_DISTRICT
            and player.travel_destination is None
            and player.jail_until is None
            and player.hospital_until is None
        ),
    )


# ------------------------------------------------------------ crawling
#
# The game had neither of these, which is most of why searching for
# play.the-smoke.com returned nothing: the public pages are the eleven
# guides and the rules, and nothing anywhere advertised that they exist.
#
# Neither file makes Google index the site -- only submitting the domain
# in Search Console and earning some inbound links does that. These just
# make sure that once a crawler does arrive, it can find everything.

SEO_PUBLIC_PATHS = (
    ("/", "1.0", "daily"),
    ("/forum", "0.9", "weekly"),
    ("/rules", "0.7", "monthly"),
    ("/register", "0.6", "monthly"),
    ("/login", "0.4", "monthly"),
)


@app.route("/robots.txt")
def robots():
    """Let everything public be crawled, keep the private half out.

    Disallow here is about crawl budget and tidiness, not security --
    every one of these paths is already behind a session check. A
    crawler that ignores this file still gets a redirect to /login.
    """
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        "Disallow: /logout",
        "Disallow: /verify-email",
        "Disallow: /reset-password",
        "Disallow: /healthz",
        "",
        f"Sitemap: {url_for('sitemap', _external=True)}",
    ]
    return Response(
        "\n".join(lines) + "\n",
        mimetype="text/plain",
    )


@app.route("/sitemap.xml")
def sitemap():
    """Every public URL, including all eleven guides.

    The guides are the only substantial prose on the site and the only
    thing that could plausibly rank for anything, so they are listed
    individually rather than left to be discovered by following links.
    """
    urls = [
        (url_for("home", _external=True).rstrip("/") + path
         if path != "/" else url_for("home", _external=True),
         priority, frequency)
        for path, priority, frequency in SEO_PUBLIC_PATHS
    ]
    urls.extend(
        (
            url_for("forum_guide", slug=guide.slug, _external=True),
            "0.8",
            "monthly",
        )
        for guide in HANDBOOK_GUIDES
    )

    entries = "".join(
        "<url>"
        f"<loc>{escape(location)}</loc>"
        f"<changefreq>{frequency}</changefreq>"
        f"<priority>{priority}</priority>"
        "</url>"
        for location, priority, frequency in urls
    )

    return Response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>",
        mimetype="application/xml",
    )


@app.route("/forum")
def forum():
    return render_template(
        "forum.html",
        player=_optional_player(),
        sections=handbook_sections(),
    )


@app.route("/forum/<slug>")
def forum_guide(slug):
    guide = get_guide(slug)
    if guide is None:
        return redirect(url_for("forum"))

    return render_template(
        "forum_guide.html",
        player=_optional_player(),
        guide=guide,
        blocks=guide.blocks,
        siblings=tuple(
            other for other in HANDBOOK_GUIDES
            if other.section == guide.section and other.slug != guide.slug
        ),
        inline=handbook_inline,
    )


@app.route("/rules")
def rules():
    return render_template(
        "rules.html",
        player=_optional_player(),
        rules=HANDBOOK_RULES,
        intro=HANDBOOK_INTRO,
        closing=HANDBOOK_CLOSING,
        inline=handbook_inline,
    )


@app.route("/city")
def city():
    if "user_id" not in session:
        return redirect("/login")

    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")

    player = Player(*player_data)
    update_travel(player)
    update_player_status(player)
    save_player(player)

    return render_template(
        "city.html",
        player=player,
        sections=city_directory(player.current_district),
        here=DISTRICTS_BY_KEY[player.current_district].name
        if player.current_district in DISTRICTS_BY_KEY
        else player.current_district.title(),
        district_names={
            key: district.name
            for key, district in DISTRICTS_BY_KEY.items()
        },
    )


GUN_BAZAAR_KEY = "kingsland_arms"

# How many the quantity box starts on. Guns are bought one at a time;
# rounds are bought by the handful.
DEFAULT_BUY_QUANTITY = {"guns": 1, "ammo": 50}


def _bazaar_lines(shop, player):
    """Decorate the venue payload with what the counter needs to show."""
    inventory = getattr(player, "inventory", {}) or {}
    lines = []
    for line in shop["items"]:
        definition = ITEMS_BY_KEY[line["key"]]
        group = "ammo" if definition.key in AMMO_KEYS else "guns"
        default = DEFAULT_BUY_QUANTITY[group]
        lines.append({
            **line,
            "group": group,
            "strength_bonus": definition.strength_bonus,
            "ammo_name": (
                ITEMS_BY_KEY[definition.ammo_key].name
                if definition.ammo_key else None
            ),
            "owned": inventory.get(definition.key, 0),
            "default_quantity": max(1, min(default, line["stock"] or 1)),
        })
    return {**shop, "items": tuple(lines)}


@app.route("/bazaar", methods=["GET", "POST"])
def gun_bazaar():
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

    if request.method == "POST":
        try:
            quantity = int(request.form.get("quantity", "0"))
            result = purchase_at(
                session["user_id"],
                GUN_BAZAAR_KEY,
                request.form.get("item_key", ""),
                quantity,
            )
            message = (
                f"Bought {result['quantity']} × "
                f"{result['item'].name} for £{result['total']:,}."
            )
            record_player_action(
                "bazaar_purchase",
                message,
                {
                    "shop": GUN_BAZAAR_KEY,
                    "item_key": result["item"].item_key,
                    "quantity": result["quantity"],
                    "total": result["total"],
                },
            )
            player = Player(*get_player_by_user_id(session["user_id"]))
        except (ValueError, ShopError) as shop_error:
            error = str(shop_error)

    shop = get_venue(GUN_BAZAAR_KEY)
    return render_template(
        "bazaar.html",
        player=player,
        shop=_bazaar_lines(shop, player),
        equipment=get_equipment_summary(player.id),
        message=message,
        error=error,
        accessible=(
            player.current_district == shop["district"]
            and player.travel_destination is None
            and player.jail_until is None
            and player.hospital_until is None
        ),
    )


FORECOURT_DISTRICT = "brixton"


@app.route("/motors", methods=["GET", "POST"])
def motors():
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
    action = request.form.get("action", "buy")

    if request.method == "POST":
        try:
            if action == "sell":
                sold, paid = sell_vehicle(
                    session["user_id"],
                    int(request.form.get("owned_id", "0")),
                )
                message = f"Sold the {sold.name} for £{paid:,}."
                record_player_action(
                    "vehicle_sold", message, {"key": sold.key}
                )
            elif action == "drive":
                set_active(
                    session["user_id"],
                    int(request.form.get("owned_id", "0")),
                )
                message = "That is the one you are driving."
            else:
                bought = buy_vehicle(
                    session["user_id"],
                    request.form.get("vehicle_key", ""),
                )
                message = (
                    f"The {bought.name} is yours "
                    f"for £{bought.price:,}."
                )
                record_player_action(
                    "vehicle_bought", message, {"key": bought.key}
                )
            player = Player(*get_player_by_user_id(session["user_id"]))
        except VehicleError as vehicle_error:
            error = str(vehicle_error)
        except ValueError:
            error = "That is not one of the cars."

    garage = garage_for(session["user_id"])

    return render_template(
        "motors.html",
        player=player,
        garage=garage,
        stock=VEHICLES,
        resale=resale_value,
        stop_chance=stop_chance,
        pulled_over_minutes=PULLED_OVER_SECONDS // 60,
        message=message,
        error=error,
        accessible=(
            player.current_district == FORECOURT_DISTRICT
            and player.travel_destination is None
            and player.jail_until is None
            and player.hospital_until is None
        ),
    )


@app.route("/blackmarket", methods=["GET", "POST"])
def black_market():
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

    if request.method == "POST":
        try:
            result = sell_to_fence(
                session["user_id"],
                player.current_district,
                request.form.get("item_key", ""),
                int(request.form.get("quantity", "0")),
            )
            message = (
                f"Sold {result['quantity']} × {result['item'].name} "
                f"for £{result['payout']:,}."
            )
            record_player_action(
                "fence_sale",
                message,
                {
                    "fence": result["fence"].key,
                    "item_key": result["item"].key,
                    "quantity": result["quantity"],
                    "payout": result["payout"],
                },
            )
            player = Player(*get_player_by_user_id(session["user_id"]))
        except (ValueError, FenceError) as fence_error:
            error = str(fence_error)

    fence = get_fence(player.current_district)
    inventory = getattr(player, "inventory", {}) or {}

    return render_template(
        "blackmarket.html",
        player=player,
        fence=fence,
        fence_base=FENCE_RATE,
        fence_speciality=SPECIALITY_RATE,
        offers=sorted(
            (
                {
                    "item": ITEMS_BY_KEY[key],
                    "quantity": quantity,
                    "unit_price": fence_price(ITEMS_BY_KEY[key], player.current_district),
                    "premium": (
                        fence is not None
                        and ITEMS_BY_KEY[key].category in fence.specialities
                    ),
                }
                for key, quantity in inventory.items()
                if key in ITEMS_BY_KEY
            ),
            key=lambda offer: -offer["unit_price"] * offer["quantity"],
        ),
        message=message,
        error=error,
        accessible=(
            player.travel_destination is None
            and player.jail_until is None
            and player.hospital_until is None
        ),
    )


@app.route("/market", methods=["GET", "POST"])
def item_market():
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

    if request.method == "POST":
        action = request.form.get("action", "")

        try:
            if action == "list":
                result = create_listing(
                    session["user_id"],
                    request.form.get("item_key", ""),
                    int(request.form.get("quantity", "0")),
                    int(request.form.get("price_each", "0")),
                )
                message = (
                    f"Listed {result['quantity']} × {result['item'].name} "
                    f"at £{result['price_each']:,} each."
                )
            elif action == "buy":
                result = buy_listing(
                    session["user_id"],
                    int(request.form.get("listing_id", "0")),
                )
                message = (
                    f"Bought {result['quantity']} × {result['item'].name} "
                    f"for £{result['total']:,}."
                )
            elif action == "cancel":
                result = cancel_listing(
                    session["user_id"],
                    int(request.form.get("listing_id", "0")),
                )
                message = (
                    f"Delisted {result['quantity']} × {result['item'].name}."
                )
            else:
                raise MarketError("Unknown market action.")

            record_player_action(f"market_{action}", message)
            player = Player(*get_player_by_user_id(session["user_id"]))
        except (ValueError, MarketError) as market_error:
            error = str(market_error)

    inventory = getattr(player, "inventory", {}) or {}

    return render_template(
        "market.html",
        player=player,
        listings=get_open_listings(session["user_id"]),
        sellable=sorted(
            (
                {
                    "item": ITEMS_BY_KEY[key],
                    "quantity": quantity,
                    "floor": minimum_price(ITEMS_BY_KEY[key]),
                }
                for key, quantity in inventory.items()
                if key in ITEMS_BY_KEY
            ),
            key=lambda offer: offer["item"].name,
        ),
        commission_percent=int(COMMISSION_RATE * 100),
        accessible=(
            player.jail_until is None
            and player.hospital_until is None
        ),
        message=message,
        error=error,
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
            "cancel_shift",
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
            elif action == "cancel_shift":
                cancelled = cancel_shift(player)
                message = (
                    f"You left after {cancelled.percent_worked}% "
                    f"of the shift and were paid "
                    f"£{cancelled.salary:,} with "
                    f"{cancelled.work_xp} XP."
                )
                if cancelled.promoted_to is not None:
                    promoted = get_job_role(
                        cancelled.promoted_to
                    )
                    message += (
                        f" Promoted to {promoted.name}."
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


# Which properties have artwork a browser can actually render. The
# first set shipped as unreadable bytes carrying an image extension, so
# "the file is there" is not the question worth asking. Resolved once
# at import; the page falls back to a drawn placeholder for the rest.
HOUSING_ARTWORK_DIRECTORY = "images/housing"


def _usable_housing_artwork():
    folder = Path(app.static_folder) / HOUSING_ARTWORK_DIRECTORY
    return frozenset(
        residence.key
        for residence in RESIDENCES
        if is_renderable_image(folder / f"{residence.key}.webp")
    )


_HOUSING_ARTWORK = _usable_housing_artwork()


@app.route("/housing", methods=["GET", "POST"])
def housing():
    if "user_id" not in session:
        return redirect("/login")
    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")
    player = Player(*player_data)
    notice = None
    error = None

    if request.method == "POST":
        try:
            # The repository moves the money and the player together, so
            # the reload below -- not save_player -- is what this page
            # renders from. Writing the snapshot back would undo it.
            residence, _remaining = move_house(
                session["user_id"],
                request.form.get("residence_key", ""),
            )
            notice = (
                f"Moved in. £{residence.purchase_price:,} paid."
            )
            player = Player(
                *get_player_by_user_id(session["user_id"])
            )
        except HousingError as housing_error:
            error = str(housing_error)

    return render_template(
        "housing.html",
        player=player,
        residences=RESIDENCES,
        artwork=_HOUSING_ARTWORK,
        # The bare address, without whatever the player has fitted --
        # this is the ladder, not their own home.
        happiness_bonus=lambda home: recovery_bonus(home, (), "happiness"),
        notice=notice,
        error=error,
    )


@app.route("/housing/manage", methods=["GET", "POST"])
def manage_housing():
    if "user_id" not in session:
        return redirect("/login")
    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")
    player = Player(*player_data)
    notice = error = None

    if request.method == "POST":
        try:
            if request.form.get("action") == "safe_deposit":
                left = safe_deposit(
                    session["user_id"],
                    int(request.form.get("amount", "0")),
                )
                notice = f"Put away. The safe holds £{left:,}."
                player = Player(
                    *get_player_by_user_id(session["user_id"])
                )
            elif request.form.get("action") == "safe_withdraw":
                left = safe_withdraw(
                    session["user_id"],
                    int(request.form.get("amount", "0")),
                )
                notice = f"Taken out. The safe holds £{left:,}."
                player = Player(
                    *get_player_by_user_id(session["user_id"])
                )
            elif request.form.get("action") == "pay_upkeep":
                paid, left = pay_upkeep(session["user_id"])
                notice = (
                    f"Rent paid, £{paid:,}."
                    if not left
                    else f"£{paid:,} paid, £{left:,} still owing."
                )
            else:
                facility, _remaining = install_facility(
                    session["user_id"],
                    request.form.get("facility_key", ""),
                )
                notice = (
                    f"Installed {facility[0]} for £{facility[1]:,}."
                )
            player = Player(
                *get_player_by_user_id(session["user_id"])
            )
        except (HousingError, SafeError, ValueError) as housing_error:
            error = str(housing_error)

    # Read once, after any purchase above has landed, so the figures
    # shown are the ones the player has just paid for.
    fitted = facilities_for(session["user_id"])
    home = get_residence(player.residence_key)

    return render_template(
        "housing_manage.html",
        player=player,
        residence=get_residence(player.residence_key),
        artwork=_HOUSING_ARTWORK,
        facilities=FACILITIES,
        owned_facilities=fitted,
        # What this player's home is actually doing for them, fittings
        # included -- the ladder page shows the bare address instead.
        comfort=comfort_for(home, fitted),
        happiness_bonus=recovery_bonus(home, fitted, "happiness"),
        energy_bonus=recovery_bonus(home, fitted, "energy"),
        nerve_bonus=recovery_bonus(home, fitted, "nerve"),
        gym_bonus=gym_gain_bonus(fitted),
        upkeep=upkeep_for(session["user_id"]),
        safe=safe_for(session["user_id"]),
        notice=notice,
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
                request.form.get(
                    "mode_key",
                    DEFAULT_TRANSPORT_KEY,
                ),
                vehicle=active_vehicle(player.id),
            )
            destination = get_district(
                journey.destination_key
            )
            message = (
                f"{journey.mode_name} to {destination.name}. "
                + (
                    "No fare."
                    if not journey.cost
                    else f"£{journey.cost:,} fare paid."
                )
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
    driven = active_vehicle(player.id)
    destinations = []

    if active_travel is None:
        for district in DISTRICTS:
            if district.key == current.key:
                continue

            route = get_travel_route(
                current.key,
                district.key,
            )
            locked = player.level < district.minimum_level
            modes = list(available_modes(current.key, district.key))
            underground_runs = len(modes) == 3
            if driven is not None:
                # Appended, so the tube keeps its place in the list and
                # the car reads as the extra option it is.
                modes.append(driving_mode(driven))
            destinations.append({
                "district": district,
                "locked": locked,
                # Cheapest first, so the free option leads.
                "options": [
                    {
                        "mode": mode,
                        "fare": mode.fare(route),
                        "duration_seconds": mode.duration_seconds(route),
                        "affordable": (
                            player.money >= mode.fare(route)
                        ),
                        "stop_chance": (
                            stop_chance(driven, player.wanted_level)
                            if mode.key == DRIVE_KEY else 0
                        ),
                    }
                    for mode in modes
                ],
                "no_underground": not underground_runs,
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
        driven=driven,
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
    # Read once for the whole request: the same figure has to reach the
    # preview and the training itself, or the page advertises a gain it
    # does not award.
    home_gains = gym_gain_bonus(facilities_for(session["user_id"]))

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
                # Energy per train varies by gym, so the definition has
                # to be resolved before the form value can be read as
                # a number of trains.
                gym_definition = get_gym(gym_key)

                if gym_definition is None:
                    raise UnknownGymError("Gym does not exist.")

                energy = (
                    int(raw_trains)
                    * gym_definition.energy_per_train
                    if raw_trains is not None
                    else int(
                        request.form.get("energy", "0")
                    )
                )
                select_gym(player, gym_key)
                trained = train(
                    player,
                    stat,
                    energy=energy,
                    gym_key=gym_key,
                    home_bonus_percent=home_gains,
                )

                if trained:
                    trained_stat = stat
                    message = (
                        f"{trained.trains} × "
                        f"{gym_definition.exercise_for(stat)}. "
                        f"{stat.title()} "
                        f"+{trained.stat_gain:g}, "
                        f"energy −{trained.energy_spent}"
                    )
                    if trained.happiness_spent:
                        message += (
                            f", happiness −"
                            f"{trained.happiness_spent}"
                        )
                    message += "."
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
        # Per gym, not one figure for the page: a district can hold
        # gyms of different weight classes, and one number would be
        # wrong for all but one of them.
        max_trains={
            gym.key: player.energy // gym.energy_per_train
            for gym in gyms
        },
        train_previews={
            gym.key: {
                stat: calculate_training_gain(
                    gym.key,
                    stat,
                    gym.energy_per_train,
                    player=player,
                    home_bonus_percent=home_gains,
                )
                for stat in VALID_BATTLE_STATS
                if gym.trains(stat)
            }
            for gym in gyms
        },
        # Happiness now costs half the energy spent, so it varies
        # by weight class rather than being one figure for the page.
        happiness_per_train={
            gym.key: happiness_cost(gym.energy_per_train)
            for gym in gyms
        },
        gain_scale_max=GAIN_SCALE_MAX,
        gain_bar_segments=GAIN_BAR_SEGMENTS,
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
    crime_progression = {
        crime.key: crime_progression_for(
            player,
            crime,
            happiness_penalty=crime_success_penalty(player),
        )
        for crime in district_crimes
    }
    return render_template(
        "crimes.html",
        player=player,
        crimes=district_crimes,
        result=result,
        attempted_crime_key=attempted_crime_key,
        error=error,
        work_shift=work_shift,
        crime_block_reason=crime_block_reason,
        crime_progression=crime_progression,
        crime_tools=tools_for,
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
    rounds_spent = ()

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
            rounds_spent = spend_ammo(player, equipment)
            record_encounter(
                player.id,
                fought_opponent.key,
                result.victory,
            )
            # Street fights count towards the daily contracts too.
            # They used to count for nothing, which made the whole board
            # unreachable on a server without an opponent to attack.
            record_contract_fight(player.id, result)
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
        rounds_spent=rounds_spent,
        energy_cost=COMBAT_ENERGY_COST,
        block_reason=get_combat_block(player),
        result=result,
        error=error,
    )



def _settle_fight(player, defender, fight, outcome):
    """Book a finished turn-by-turn fight the way a one-shot one was.

    Rating, contracts, the activity feed and the aftermath all read a
    result object, so the fight is turned back into one rather than
    teaching four callers about a new shape. The cash is zero here on
    purpose -- what the winner takes is still their choice, settled
    afterwards.
    """
    victory = bool(outcome.victory)
    xp_reward = 0

    if victory:
        xp_reward = (
            0
            if fight.reward_multiplier <= 0
            else max(5, int((20 + defender.level * 4)
                            * fight.reward_multiplier))
        )
        award_xp(player, xp_reward)
    else:
        player.health = 0
        send_to_hospital(player, PVP_HOSPITAL_SECONDS)

    player.health = outcome.attacker_health if victory else 0
    if victory:
        defender.health = 0

    save_player(player)
    save_player(defender)

    result = SimpleNamespace(
        victory=victory,
        attacker_health=outcome.attacker_health,
        defender_health=outcome.defender_health,
        cash_stolen=0,
        xp_reward=xp_reward,
        rounds=tuple(
            SimpleNamespace(
                round_number=entry["turn"],
                actor="attacker" if entry["attacker_event"] == "hit" else "defender",
                event=entry["attacker_event"],
                damage=entry["attacker_damage"],
                attacker_health=entry["attacker"],
                defender_health=entry["defender"],
            )
            for entry in fight.log
        ),
        hospital_until=None,
        attacker_start_health=fight.attacker_max_health,
        attacker_max_health=fight.attacker_max_health,
        defender_start_health=fight.defender_max_health,
        defender_max_health=fight.defender_max_health,
    )

    rating_update = record_pvp_attack(
        player.id, defender.id, fight.approach,
        result, fight.reward_multiplier,
    )
    record_contract_fight(
        player.id, result, fight.approach, rated=rating_update.rated
    )
    record_player_action(
        "pvp_combat",
        f"{'Defeated' if victory else 'Lost to'} {defender.name}.",
        {
            "defender_id": defender.id,
            "victory": victory,
            "turns": outcome.turn,
            "xp_reward": xp_reward,
            "approach": fight.approach,
        },
    )

    return result, rating_update


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
    rating_update = None
    defender = None
    error = None
    attacker_equipment = None
    defender_equipment = None
    rounds_spent = ()
    selected_approach = request.form.get("approach", "balanced")
    if selected_approach == "balanced":
        selected_approach = "defensive"

    aftermath = None
    burglary = None

    if request.method == "POST" and request.form.get("action") == "aftermath":
        # A fight that has already been won; this only decides what
        # happens to the person on the floor.
        try:
            aftermath = settle_aftermath(
                int(request.form.get("attack_id", "0")),
                player.id,
                request.form.get("choice", ""),
            )
            player = Player(*get_player_by_user_id(session["user_id"]))
        except (PvpError, ValueError) as settle_error:
            error = str(settle_error)

    elif request.method == "POST" and request.form.get("action") == "burgle":
        # Crime-shaped, not combat-shaped: nerve, not energy, and a
        # cell rather than a hospital bed when it goes wrong.
        try:
            burglary = burgle(
                session["user_id"],
                int(request.form.get("target_id", "0")),
            )
            player = Player(*get_player_by_user_id(session["user_id"]))
        except (BurglaryError, ValueError) as break_in_error:
            error = str(break_in_error)

    elif request.method == "POST" and request.form.get("action") == "flee":
        try:
            walked = get_open_fight(player.id)
            flee_fight(int(request.form.get("fight_id", "0")), player.id)
            if walked is not None:
                # The reservation is only cleared when an attack is
                # recorded. Walking away records nothing, so without
                # this the target stays locked to a fight that ended.
                release_pvp_attack(player.id, walked.defender_id)
        except (PvpError, ValueError) as flee_error:
            error = str(flee_error)

    elif request.method == "POST" and request.form.get("action") == "turn":
        # One swing. The fight is already open; this only advances it.
        try:
            fight = get_open_fight(player.id)
            if fight is None:
                raise PvpError("You are not in a fight.")

            defender = Player(*get_player_by_user_id(
                get_target_user_id(fight.defender_id)
            ))
            outcome, fight = take_fight_turn(
                fight.id,
                player,
                defender,
                request.form.get("weapon", ""),
            )
            player = Player(*get_player_by_user_id(session["user_id"]))

            if outcome.finished:
                result, rating_update = _settle_fight(
                    player, defender, fight, outcome
                )
        except (PvpError, TurnError, ValueError, TypeError) as turn_error:
            error = str(turn_error)

    elif request.method == "POST":
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

            block = get_pvp_block(player, defender)
            if block is not None:
                raise PvpError(block)

            limits = reserve_pvp_attack(player.id, defender.id)

            start_fight(
                player,
                defender.id,
                defender.health,
                defender.max_health,
                selected_approach,
                reward_multiplier=limits.reward_multiplier,
            )
            player = Player(*get_player_by_user_id(session["user_id"]))
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

    pvp_profile = get_pvp_profile(player.id)
    # One query for the whole list rather than one per row: the board is
    # small, but this page already reads a lot per target.
    bounties = open_bounty_totals(target["id"] for target in targets)
    for target in targets:
        target["matchmaking"] = matchmaking_label(
            pvp_profile["rating"], target["rating"]
        )
        target["bounty"] = bounties.get(target["id"], {}).get("total", 0)
    targets.sort(
        key=lambda target: (
            target["restricted"]
            or target["beginner_protection_seconds"] > 0,
            abs(target["rating"] - pvp_profile["rating"]),
            target["name"].casefold(),
        )
    )

    notifications = get_unread_pvp_notifications(player.id)
    if notifications:
        mark_pvp_notifications_read(player.id)

    # Squaring up to somebody: the attack screen before a punch is
    # thrown. A plain link with a target on it, so it costs nothing and
    # survives a refresh.
    # Not while a fight is already going: the START FIGHT form posts to
    # the current URL, which still carries ?target_id, so without this
    # the staging screen renders on top of the fight it just started.
    open_fight = get_open_fight(player.id)
    staged_target = None
    if result is None and open_fight is None:
        try:
            staged_id = int(request.args.get("target_id", "0"))
        except ValueError:
            staged_id = 0
        if staged_id:
            staged_target = next(
                (
                    target for target in targets
                    if target["id"] == staged_id
                    and not target["restricted"]
                ),
                None,
            )

    return render_template(
        "pvp.html",
        staged_target=staged_target,
        player=player,
        targets=targets,
        approaches=APPROACHES,
        selected_approach=selected_approach,
        energy_cost=PVP_ENERGY_COST,
        block_reason=get_pvp_block(player),
        result=result,
        defender=defender,
        attacker_equipment=attacker_equipment,
        defender_equipment=defender_equipment,
        rounds_spent=rounds_spent,
        playback=build_pvp_playback(result),
        error=error,
        history=get_recent_pvp_attacks(player.id),
        notifications=notifications,
        pvp_profile=pvp_profile,
        streak_progress=get_streak_progress(pvp_profile["streak"]),
        rating_update=rating_update,
        weapons=weapons_for(player.id),
        fight=open_fight,
        maximum_turns=MAXIMUM_TURNS,
        pending_aftermath=get_pending_aftermath(player.id),
        aftermath=aftermath,
        burglary=burglary,
        burglary_nerve=BURGLARY_NERVE_COST,
        burglary_odds=odds_against,
    )



@app.route("/pvp/contracts", methods=["GET", "POST"])
def pvp_contracts():
    if "user_id" not in session:
        return redirect("/login")
    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")
    player = Player(*player_data)
    message = None
    error = None
    if request.method == "POST":
        try:
            reward = claim_contract(
                player.id,
                request.form.get("contract_key", ""),
            )
            message = (
                f"{reward.contract_name} claimed: "
                f"£{reward.cash_reward} and {reward.xp_reward} XP."
            )
            player_data = get_player_by_user_id(session["user_id"])
            player = Player(*player_data)
        except ContractClaimError as claim_error:
            error = str(claim_error)
    return render_template(
        "pvp_contracts.html",
        player=player,
        board=get_contract_board(player.id),
        message=message,
        error=error,
    )


@app.route("/pvp/bounties", methods=["GET", "POST"])
def pvp_bounties():
    if "user_id" not in session:
        return redirect("/login")
    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")
    player = Player(*player_data)
    message = None
    error = None

    if request.method == "POST":
        try:
            named = request.form.get("name", "").strip()
            target_id = find_target(named)
            if target_id is None:
                raise BountyError(
                    f"Nobody in London goes by \u201c{named}\u201d."
                    if named else "Name somebody."
                )
            posted = post_bounty(
                session["user_id"],
                target_id,
                int(request.form.get("amount", "0")),
            )
            message = (
                f"£{posted.amount:,} is on {posted.target_name}. "
                f"The fixer took £{posted.fee:,}."
            )
            player = Player(*get_player_by_user_id(session["user_id"]))
            record_player_action(
                "bounty_posted",
                f"Put £{posted.amount:,} on {posted.target_name}.",
                {"amount": posted.amount},
            )
        except BountyError as bounty_error:
            error = str(bounty_error)
        except ValueError:
            error = "Name a whole number of pounds."

    # One settlement per page view, and the readers below filter
    # lapsed bounties out themselves -- so what this decides is when a
    # poster gets their stake back, not what the board shows.
    sweep()

    return render_template(
        "pvp_bounties.html",
        player=player,
        board=get_board(player.id),
        mine=bounties_posted_by(player.id),
        standing=total_open(),
        prefill=request.args.get("name", ""),
        minimum=BOUNTY_MINIMUM,
        maximum=BOUNTY_MAXIMUM,
        fee_percent=BOUNTY_FEE_PERCENT,
        lifetime_days=BOUNTY_LIFETIME_DAYS,
        total_cost=total_cost,
        posting_fee=posting_fee,
        message=message,
        error=error,
    )


@app.route("/pvp/leaderboard")
def pvp_leaderboard():
    if "user_id" not in session:
        return redirect("/login")
    player_data = get_player_by_user_id(session["user_id"])
    if player_data is None:
        return redirect("/login")
    player = Player(*player_data)
    scope = request.args.get("scope", "district")
    district = (
        player.current_district
        if scope == "district"
        else None
    )
    return render_template(
        "pvp_leaderboard.html",
        player=player,
        scope=scope,
        leaderboard=get_pvp_leaderboard(district=district),
        profile=get_pvp_profile(player.id),
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

    if not get_operations_settings().registration_open:
        return render_template(
            "error.html",
            title="Registrations temporarily paused",
            message=(
                "New accounts are not being accepted right now. "
                "Please check back soon."
            ),
        ), 403

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

        # One message for both, and the same work done either way.
        # Saying "user not found" hands over a list of real accounts,
        # and returning early does it again through timing: skipping
        # bcrypt answers in a millisecond where a real account takes
        # nearly three hundred.
        if user is None or not verify_password(password, user[3]):
            if user is None:
                verify_password(password, ABSENT_USER_PASSWORD_HASH)
            error = "Those details do not match an account."

        elif is_user_suspended(user[0]):
            error = (
                "This account has been suspended. "
                "Contact support if you believe this is an error."
            )

        elif is_account_blocked(user[0]):
            error = (
                "This account has been suspended or banned. "
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
