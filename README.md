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
python3 -m unittest discover -s tests            # 1,017 tests
python3 -m compileall -q app.py main.py auth cli database game tests web scripts
```

**One command, and it runs everything.** That was not true until recently:
`tests/auth/` had no `__init__.py`, so discovery walked past all six files in
it — every check on password hashing, login timing and the admin rate limit,
passing on demand and never once on a push. Adding the `__init__.py` made it
worse, because `discover -s tests` puts `tests/` on the front of the path and
`tests/auth` then *replaced* the real `auth` package, killing seventy-seven
unrelated tests with `No module named 'auth.email_delivery'`.

The directory is now `tests/authentication/`, which collides with nothing.
`tests/test_suite_integrity.py` fails if a test directory is ever named after a
real package again, and names the directory rather than leaving you to work it
out from an import error seventy-seven files deep.

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
  currently at 54). `create_tables()` runs at import of `web/application.py`, so a
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

### 5. The CSS cache-bust must be bumped in every template at once

Templates link `style.css` with a `v=` query string. All 43 now agree on one
token (`landing-1`), which they did not always. **If you edit `style.css`, bump
the version in every template**, or the un-bumped pages will serve stale CSS to
returning players:

```bash
find web/templates -name '*.html' -exec \
  sed -i "s/style\.css', v='[^']*'/style.css', v='NEW-TOKEN'/g" {} +
```

### 6. The economics were solved numerically, not guessed

Casino paytables were derived — exhaustive enumeration over all reel combinations
for slots, hypergeometrically for keno, and a 200,000-round simulation for
blackjack. The tests recompute the return on every run and fail if a payout is
edited without the maths being redone. **Do not hand-tune a payout.** A drift here
mints or destroys money silently and no player will report getting richer.

---

### 7. Production runs a newer Python than your sandbox

**Production is on Python 3.14. A dev container may well be on 3.11.** That gap
is not cosmetic — it silently hid a live 500 on `/fight` in August 2026.

Gym training stores fractional stats on purpose (`round(gain, 2)`, so strength
is 84.35, not 84), and combat hands those to `random.randint`. Until Python 3.12,
`randrange` accepted a float that happened to be whole, so `randint(0, 47.0)`
worked and `randint(0, 47.9)` raised. **3.12 removed the allowance; 3.14 raises
`TypeError` on both.** Every fight passed locally while real players got a 500.

`game/combat/stats.py:whole()` settles stats to integers at the top of each
fight. More importantly, `tests/gameplay/test_fractional_stats.py` defines
`StrictRandom`, which enforces 3.12+ rules **on whatever interpreter the suite is
running**, so this class of bug fails here rather than in production. Do not relax
it to make a test pass — it stands in for the live interpreter.

To sweep the whole suite under those rules:

```python
# monkeypatch random.Random.randint to reject non-int args, then
# unittest.defaultTestLoader.discover("tests")
```

> **Before trusting "all green", check `python3 -V` against the server.** Anything
> version-sensitive — `random`, `datetime` parsing, `int`/`float` coercion — can
> pass here and fail there.

## What changed recently

Newest first. Every entry is a merged PR; `git log` has the detail.

**Live fixes**
- **#155** — four holes found auditing the live site: the admin login had no rate
  limit, a missing account answered faster than a wrong password (279ms against
  1ms, which enumerates the user list), the session secret could fall back to a
  fixed string, and the app served no security headers.
- **#153** — fighting crashed for anybody who had trained. Trained stats are
  floats; Python 3.12 stopped letting `randint` take one. The local suite passed
  on 3.11 while production 500'd on 3.14 — Trap 7, in the wild.
- **#152** — the `/fight` page 500'd for exactly the players who could not use it:
  every guard handled a missing opponent except the last one.
- **#141** — SQLite moved to write-ahead logging. Every page load writes (the
  loader settles regeneration clocks), so on the default rollback journal the
  whole site serialised behind whoever was committing. Measured 794 → 2,820 page
  loads/sec at eight concurrent workers. `synchronous` deliberately left at `FULL`.
- **#140** — the two registration 500s described in Traps 1 and 3, plus migration
  040 to repair accounts already stranded.

**Features**
- **#159** — the last two figures on the property page that did nothing.
  **Comfort** now drives happiness recovery, which is what the gym spends
  alongside energy — so a good address buys more trains rather than bigger
  ones — and the **swimming pool** finally adds the 2% gym gains it has been
  sold for. Nothing a property advertises is decoration any more, and a test
  asserts that against the code rather than against the guide.
- **#156** — two things that give the rest of the game something to push
  against.
  **The bounty board**: anybody can put £500–£250,000 on any player's head;
  the stake is escrowed on posting, the fixer takes 10% on top as a sink, and
  it is collected by whoever beats that player and chooses *hospitalise*.
  Unclaimed after seven days it lapses and the stake goes back. This also fixed
  the aftermath screen, where mugging used to strictly dominate because it paid
  and the other two choices did not.
  **Coldharbour Motors**: seven vehicles in Brixton, kept in the garage the
  property page had been advertising since housing shipped. A car is faster
  than the bus, cheaper than the fare and reaches Hackney where the tube does
  not — but it is the only way across London the police can stop, on odds of
  your wanted level against how much the car shows off. Heat now has a second
  consequence.
- **#155** — the safe and the burglar. Three places to keep money and only one
  of them grows: the bank is untouchable and earns nothing, the safe pays 0.25%
  a day and can be broken into, pockets are what a mugger takes. Plus the five
  crime tools that had sat in the shop doing nothing since launch.
- **#154** — player fights rebuilt as a turn-by-turn attack screen: you pick a
  weapon each turn from your real loadout, with ammunition and throwables spent
  as you use them, and dedicated melee and throwable slots to carry them in.
- **#152** — the two economy gaps. Crime rewards were flat across the ladder
  (1.72× from bottom to top, now 3.38×), and the daily contract board was paying
  £0 because it only counted rated player fights on a server with almost no
  players. The gym ladder was re-priced in the same PR: the top gym went from
  1,284 days of income to 205.
- **#150** — rent. Housing had been a one-off purchase; now every home charges
  £150–£550 a day, accrued from elapsed time like every other clock here.
- **#149** — a reason to leave Camden. **#151** — the landing page, `robots.txt`
  and a sitemap, because the site was not in the index at all.
- **#140** — Ronnie Dell, the loan shark in Soho. £5,000 a level from level 3 at
  2.5%/day, interest accrued by the second, payment due every three days. Missing
  one is a hospital stay that escalates 30min → 2h → 6h → 12h while the debt stays
  put. Collection runs on every request so it cannot be dodged.
- **#139** — the handbook: guides at `/forum`, rules at `/rules`, both public.
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
Hackney — 48 items, 7 vehicles, 14 guides, 54 migrations.

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
