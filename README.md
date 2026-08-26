# The Smoke

A text-based London crime RPG in the shape of Torn. Flask, SQLite, server-rendered
Jinja. Live at [play.the-smoke.com](https://play.the-smoke.com) with real players
and real balances — treat `main` as production.

**This file is written for whoever picks the work up next, human or agent.** It is
orientation and hazards, not a tour. The reference docs already exist and are
listed at the bottom; what follows is the part that is not written down anywhere
else, including three things that have already caused live incidents.

---

## Start here

```bash
python3 app.py                                   # serve on :5000
python3 -m unittest discover -s tests            # 571 tests
```

**The suite is bigger than it looks.** `tests/auth/` has **no `__init__.py`**, so
`unittest discover` silently skips all five files in it. This is deliberate, it is
easy to miss, and it means "all green" from discovery alone is not all green:

```bash
for f in tests/auth/test_*.py; do
  python3 -m unittest "$(echo "$f" | sed 's|/|.|g; s|\.py$||')"
done
python3 -m compileall -q app.py main.py auth cli database game tests web scripts
```

Only two dependencies — `bcrypt` and `Flask` — and that is on purpose. Catalogues
are structured Python, not YAML or JSON loaded at runtime. Think hard before
adding a third.

---

## Rules that are not optional

- **Pure rules live in `game/`. It contains no SQL.** Every query lives in
  `database/repositories/`. This separation is what makes the game testable
  without a database, and it is worth defending.
- **All money moves inside `BEGIN IMMEDIATE`.** No exceptions. See
  `database/repositories/casino.py` or `loans.py` for the shape.
- **Migrations are ordered and idempotent** (`database/core/migrations.py`,
  currently at 41). `create_tables()` runs at import of `web/application.py`, so a
  service restart applies them. Never edit a migration that has shipped — add a
  new one.
- **Nothing is scheduled.** Energy, nerve, happiness, health, wanted level and
  loan interest all accrue lazily from elapsed time when the player is next
  loaded. There is no cron, no background worker, and there should not be one.
- **Pages work without JavaScript.** Every action is a form POST that renders a
  full page. The JS is progressive enhancement — the casino sends
  `X-Requested-With: casino` to get JSON for its animations, and falls back
  cleanly. Keep it that way.

---

## Traps that have already bitten

These are real incidents, not hypotheticals.

### 1. `players` has two different schemas

A database **built fresh** from the `CREATE TABLE` has the wanted, happiness and
health clocks as `NOT NULL DEFAULT CURRENT_TIMESTAMP`. A database **upgraded
through the migrations** got those columns from `ALTER TABLE`, which cannot carry
a non-constant default — so there they are plain nullable `TEXT` with a one-off
backfill behind them.

Production is the upgraded shape. **Every test builds the fresh shape.** In August
2026 this shipped a bug where every newly registered account was written with
three `NULL` clocks and then died with `fromisoformat: argument must be str` on
the first page it opened — an account you could create and never use.

> **If you add a column to `players`, set it explicitly in `create_player`.**
> Do not rely on a column default, because only one of the two shapes has it.
> `tests/persistence/test_migrations.py` has a test that runs against the
> upgraded shape; add to it rather than trusting the fresh-schema tests.

### 2. `Player(*player_data)` is positional

`get_player_by_user_id` returns a tuple that is splatted into `Player` by
position, and the code indexes it by number (`player_data[33]`). **A new column in
that `SELECT` must be appended at the end**, or every field after it silently
shifts. This has caused more than one bug.

### 3. bcrypt reads 72 bytes and no more

Since bcrypt 4.0 it *raises* on longer input instead of trimming. `utils/security.py`
now clamps to 72 bytes, which is what the old library did, so existing hashes still
verify. Note the limit is on **bytes**: a 27-character password of emoji is 102
bytes and used to crash registration, sign-in and password reset alike. Do not
remove the clamp; do not pre-hash without a migration plan for every stored hash.

### 4. SQLite runs in WAL, so never copy `game.db` alone

A committed write lives in `game.db-wal` until a checkpoint. `cp`, `rsync` or a
snapshot taken mid-write silently loses the most recent play and you find out on
the day you restore. Use `scripts/backup_database.py`, which uses the online
backup API and includes the WAL. `deployment/README.md` says this too.

The journal mode is applied **once per process**, not per connection — the pragma
costs ~200µs against ~40µs to open the connection, and a page load opens several.

### 5. The CSS cache-bust is currently inconsistent

Templates link `style.css` with a `v=` query string. Right now 36 templates say
`casino-5` and 4 say `loans-1`. **If you edit `style.css`, bump the version in
every template**, or the un-bumped pages will serve stale CSS to returning
players. Unifying these on one token would be a welcome small cleanup.

### 6. The economics were solved numerically, not guessed

Casino paytables were derived — exhaustive enumeration over all reel combinations
for slots, hypergeometrically for keno, and a 200,000-round simulation for
blackjack. The tests recompute the return on every run and fail if a payout is
edited without the maths being redone. **Do not hand-tune a payout.** A drift here
mints or destroys money silently and no player will report getting richer.

---

## What changed recently

Newest first. Every entry is a merged PR; `git log` has the detail.

**Live fixes**
- **#141** — SQLite moved to write-ahead logging. Every page load writes (the
  loader settles regeneration clocks), so on the default rollback journal the
  whole site serialised behind whoever was committing. Measured 794 → 2,820 page
  loads/sec at eight concurrent workers. `synchronous` deliberately left at `FULL`.
- **#140** — the two registration 500s described in Traps 1 and 3, plus migration
  040 to repair accounts already stranded.

**Features**
- **#140** — Ronnie Dell, the loan shark in Soho. £5,000 a level from level 3 at
  2.5%/day, interest accrued by the second, payment due every three days. Missing
  one is a hospital stay that escalates 30min → 2h → 6h → 12h while the debt stays
  put. Collection runs on every request so it cannot be dodged.
- **#139** — the handbook: 10 guides at `/forum`, rules at `/rules`, both public.
  Reachable from a burger menu beside the brand on every page.
- **#135–#138** — the Golden Square casino: slots, keno and blackjack, with reel
  and card animations, and the result held back until the animation reaches it.
- **#133–#134** — four low-calibre pistols, three calibres of ammunition (a gun
  with no rounds contributes nothing in combat), the Kingsland Arms bazaar in
  Hackney, and the City directory that replaced an overgrown nav bar.
- **#130–#132** — crime loot and the black-market fence, the global item market,
  and three travel modes (walk free/slow, bus standard, Underground double fare
  and half time — no Underground to Hackney).
- **#125–#129** — the gym reworked into Torn-style weight classes, gains scaled by
  stat, fourteen gyms re-tiered by price, plus Shoreditch and Hackney.

**Shape of the world**: five districts — Camden, Brixton, Soho, Shoreditch,
Hackney — 44 items, 10 guides, 41 migrations.

---

## Known gaps, honestly

Worth reading before planning anything new.

- **Crime progression is deliberately bounded.** Individual crime mastery adds
  at most 8 percentage points to success and district reputation adds at most
  15% cash. Level remains an unlock rather than a global payout multiplier, so
  high-level players still need to move into harder districts for larger rewards.
- **PvP daily contracts are worth £0 on a small server.** They pay £575–750/day
  but only count rated player-vs-player fights, and the population is tiny.
  Making NPC fights count would be a small fix.
- **Five utility items do nothing** — lockpick, duct tape, glass cutter, bolt
  cutters, burner phone. They have resale value and appear as loot, but no
  gameplay effect.
- **Some item art is placeholder.** The cartridge images are drawn rather than
  rendered, and the Converted Blank Pistol reads as a full-size service pistol —
  larger than the Compact 9mm above it in the ladder.
- **Unmeasured feel.** The gym happiness taper, the 45% loot drop rate and the
  casino table limits were all set by judgement and have never been checked
  against real play.

---

## Reference docs

| File | What it covers |
| --- | --- |
| `docs/game_design.md` | The blueprint. Every mechanic and its numbers. Update it when you change a rule. |
| `docs/folder_structure.md` | Where things live and why |
| `docs/testing.md` | Coverage map and the test-data rule |
| `docs/database_migrations.md` | How migrations work |
| `docs/authentication.md` | Accounts, tokens, verification |
| `docs/roadmap.md` | What was planned next |
| `deployment/README.md` | The VPS, systemd, backups, maintenance mode |

**A note on working style, since the owner is not a full-time engineer**: explain
the trade-off, then act. Verify against the real app rather than tests alone —
several of the bugs above passed the whole suite. And when a number matters,
compute it rather than estimating it.
