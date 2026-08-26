# The Smoke — Game Design Blueprint

## Vision

**The Smoke** is a persistent London-based browser RPG. Development is backend-first: game rules, persistence, progression, economy and world systems are built and tested in Python before a web interface is added.

The game should support different paths to success. A player may focus on crime, legal careers, combat, business, wealth, vehicles, gangs, factions or a mixture of them.

## Design Principles

- London is part of the gameplay, not just decoration.
- Level represents overall progression and unlocks; it does not directly equal combat power.
- Player power comes from training, equipment, money, skills and choices.
- Legal progression should be viable alongside criminal progression.
- Money must have competing uses so the economy stays meaningful.
- Core game logic should remain separate from terminal or future web UI code.
- Persistent systems should use timestamps instead of requiring a process to run continuously for every player.
- Large systems should be modular and reusable by PvE, PvP, missions and future web routes.

---

## Accounts and Characters

### Users

- id
- username
- email
- password_hash
- created_at

Passwords are stored only as secure hashes.

### Players

Core identity:

- id
- user_id
- name
- level
- xp
- current_district
- created_at
- last_seen

Resources:

- money
- bank_balance
- health / max_health
- energy / max_energy
- nerve / max_nerve
- happiness / max_happiness

Battle stats are separated from the main player record:

- strength
- defence
- speed
- dexterity

Happiness is a resource stat that starts full and only falls when the
player is sent to jail or hospital. It regenerates over time like energy
and nerve, and items can restore it directly. It softens (never
strengthens) gym training gains and crime success odds when it is below
maximum, giving players a reason to stay out of trouble or top up with
consumables rather than a permanent bonus for doing nothing.

Health regenerates over time like energy and nerve, is frozen while
hospitalised, and is fully restored on discharge. `max_health` grows
with level (100 at level 1, +10 per level) so higher-level players can
absorb more punishment; a level-up that finds the player already at
full health also tops up the current value to match the new cap.

Temporary state is also separated:

- jail_until
- hospital_until
- travel_until
- wanted_level
- last_energy_update
- last_nerve_update
- last_health_update

---

## Progression

Overall level unlocks new opportunities rather than automatically making the player stronger.

Example progression:

- Level 1 — starter crimes, starter jobs and starter districts
- Level 3 — additional crimes
- Level 5 — additional gym
- Level 7 — additional jobs
- Level 10 — higher-tier districts
- Level 15 — property ownership progression
- Level 20 — advanced gang/faction content

Example XP curve:

- Level 1: 0 XP
- Level 2: 100 XP
- Level 3: 250 XP
- Level 4: 500 XP
- Level 5: 900 XP

Individual systems also have their own progression, such as crime skills, career XP, driving skill and district reputation.

---

## London Districts

Initial planned districts:

| District | Unlock | Identity | Built |
| --- | ---: | --- | :---: |
| Camden | 1 | Markets, nightlife, beginner content | yes |
| Brixton | 1 | Jobs, gyms, local gangs and street progression | yes |
| Soho | 2 | Nightlife, tourism, pickpocketing and clubs | yes |
| Shoreditch | 5 | Tech, nightlife and electronics | yes |
| Hackney | 7 | Residential crime, garages and gang activity | yes |
| The City | 10 | Finance, banking and investments | — |
| Canary Wharf | 12 | Corporate careers and expensive property | — |
| Chelsea | 15 | Luxury property and high-value opportunities | — |
| Westminster | 20 | Prestige, high security and advanced missions | — |

Districts contain their own crimes, jobs, gyms, shops, properties and reputation progression.

### Getting around

Every route can be travelled three ways, and what money buys is the time
back:

| Mode | Fare | Journey |
| --- | --- | --- |
| Walk | free | 3× the route time |
| Bus | the route fare | the route time |
| Underground | 2× the fare | half the time |

Camden to Soho is free and 15 minutes on foot, £20 and 5 minutes on the
bus, £40 and 2½ minutes on the tube.

Walking free matters most at the bottom of the game: a player with
nothing can always move, and pays in minutes they cannot spend on
anything else, since travel blocks crimes, training and work.

**The Underground does not reach Hackney** — it is Overground and buses
out east — so the fastest way there is still the bus however rich you
are. The travel page says so rather than silently hiding the option.

The catalogue in `game/world/districts.py` is the single source of truth
for districts and the routes between them, and it validates itself at
import: keys must be unique, every route must name real districts, cost
a fare and take time, and **every pair of districts must have a direct
route**. Travel offers a direct fare between any two districts, so a
missing edge would simply be a district nobody could reach.

Every district has somewhere to train. Shoreditch and Hackney carry the
top five gyms, along with a shop, a career and two crimes each.

### District Reputation

Each district has independent reputation. Reputation unlocks local opportunities and can provide modest bonuses.

---

## Travel

Players can travel by:

- walking
- bus
- Tube
- taxi
- personal vehicle

Travel may use money and/or time. Personal vehicles add flexibility but are not required to play.

Persistent travel state:

- current_district
- travel_destination
- travel_until

---

## Housing

Housing exists from the beginning of the game.

Possible starting backgrounds/residences:

- Tent / rough sleeper
- Temporary hostel
- Council flat / council estate background

Housing progression can continue through private rentals, starter flats, Camden flats, Canary Wharf apartments, Chelsea townhouses and luxury properties.

Housing can affect:

- comfort
- storage capacity
- energy recovery
- health recovery
- safe cash capacity
- garage capacity
- prestige

Housing should not provide huge direct combat bonuses.

---

## Gyms

Different London gyms specialize in different battle stats.

Core battle stats:

- Strength — damage
- Defence — damage reduction
- Speed — initiative / hit chance
- Dexterity — dodge / evasion

Gyms may differ by:

- district
- membership price
- unlock requirement
- weight class
- stat multipliers
- specialization

This allows multiple gyms without hardcoding separate training logic for each one.

### Weight classes

Every gym belongs to a weight class, which fixes how much energy one
train costs:

| Class | Energy per train | Trains per full 150 bar |
| --- | --- | --- |
| Lightweight | 5 | 30 |
| Middleweight | 10 | 15 |
| Heavyweight | 25 | 6 |

Weight class decides how big each commitment is, not how efficiently the
gym converts energy into stats — that is the multiplier's job.

**Class follows price, not district.** As in Torn, a player spends a
long run of gyms on 5 energy a train — everything up to £2,500 here —
before the commitments get bigger. Big single commitments belong to the
late game, where a player has the energy bar and the happiness to absorb
them.

### The roster

Fourteen gyms, ordered by price, level and average gain together:

| Gym | District | Price | Level | Class |
| --- | --- | ---: | ---: | --- |
| Camden Community Gym | Camden | free | 1 | Lightweight |
| Average Joe's Camden | Camden | £100 | 1 | Lightweight |
| Camden Ironworks | Camden | £250 | 1 | Lightweight |
| Brixton Barbell Club | Brixton | £500 | 2 | Lightweight |
| South London Performance | Brixton | £1,000 | 2 | Lightweight |
| Soho Fitness Rooms | Soho | £2,500 | 2 | Lightweight |
| West End Fight Lab | Soho | £5,000 | 3 | Middleweight |
| London Elite | Soho | £10,000 | 4 | Middleweight |
| The Warehouse | Shoreditch | £25,000 | 5 | Middleweight |
| Iron Yard | Shoreditch | £60,000 | 6 | Middleweight |
| The Arches | Hackney | £150,000 | 7 | Middleweight |
| Marsh Athletic | Hackney | £400,000 | 9 | Heavyweight |
| Powerhouse | Hackney | £1,000,000 | 12 | Heavyweight |
| The Lock | Hackney | £2,500,000 | 15 | Heavyweight |

A specialist can beat the gym above it on its one strong stat without
being the better gym overall — West End Fight Lab trains no speed, and
Powerhouse no dexterity — so the roster is ordered on the *average* of
the stats each gym trains, not its best one.

### Gain bars

Gains are drawn as twelve segments against a ceiling (`GAIN_SCALE_MAX`)
that sits deliberately **above** the best gym in the game: the free gym
reads 2 of 12 and the top of the roster 8 of 12. A full bar reads as
finished and forces the scale to be rewritten the moment a better gym is
added, so the ceiling is raised before that happens, never to match the
current best.

### The gain formula

```
gain = energy × gym multiplier × 0.2 × (1 + stat / 2000) × happiness
```

Following Torn's shape, gain is **linear in the stat being trained**,
with a floor so a beginner's first sessions still matter. It doubles at
2,000, triples at 4,000, and keeps going. Without that, a flat gain that
is transformative at 10 strength is invisible at 5,000 and training
stops meaning anything.

The 0.2 floor is set so the opening experience is unchanged: a new
player at Camden still gains exactly 1.0 a train.

| Stat | Camden (5 energy, ×1.0) | London Elite (25 energy, ×2.0) |
| ---: | ---: | ---: |
| 10 | 1.0 | 10.05 |
| 1,000 | 1.5 | 15.0 |
| 5,000 | 3.5 | 35.0 |
| 10,000 | 6.0 | 60.0 |

### Happiness

A train costs **half the energy it spends, rounded up** — 3 at a
lightweight gym, 5 at middleweight, 13 at heavyweight — so a full
150-energy bar costs roughly the same happiness however it is broken up.
This is Torn's rule, and it is why weight class does not gate happiness
efficiency.

Happiness then scales the gain between 0.5× and 1.0×, and floors at 0
rather than blocking training, so a drained player still trains at half
rate.

Because happiness falls and the stat rises as a batch runs, a batch
cannot be scored with one multiplier. Training is simulated one
train at a time, which also means N separate trains and one batch of N
produce exactly the same result — there is no reward for click-spamming.

### One source of truth

All of the above lives in `game/gym/formula.py`. The service, the CLI and
the web preview all call into it, so the "+N per train" the gym page
shows is the number training actually awards.

Each gym also names the exercise it trains a stat with (Camden's
"dumbbell presses", the elite gym's "olympic lifts"), which is what the
result message reports back.

---

## Operations

Operations are the story spine: a fixed chain of five jobs across London
that pays off the £2,000 debt the player starts owing. They are not
repeatable — each one is run once, and the campaign ends when the debt
does.

| # | Operation | District | Level |
| --- | --- | --- | --- |
| 1 | The Camden Collection | Camden | 1 |
| 2 | A Favour in Soho | Soho | 3 |
| 3 | The Brixton Warehouse | Brixton | 5 |
| 4 | The Camden Lockup | Camden | 8 |
| 5 | Clearing the Ledger | Soho | 12 |

Every operation offers the same three-way choice, so a player can lean on
whichever stat they have been training:

- **Persuasion** (dexterity) — cheapest, quietest, least wanted level,
  smallest payout.
- **Stealth** (speed) — the middle of everything.
- **Force** (strength) — most expensive in energy and nerve, biggest
  payout, and the loudest trail.

The approach decides the energy and nerve spent up front, how long the
operation runs for, the cash and XP on completion, the wanted level
earned, and how much of the debt it clears.

An operation opens only when the one before it is complete, the level is
reached and the player is standing in the right district. That chain is
also what keeps a player to one operation at a time: a running operation
is not a completed one, so nothing behind it can open.

The first four operations clear between £1,125 and £1,925 between them,
which is deliberately never the full £2,000 — the finale settles whatever
is left, whichever way it is played.

---

## Crimes

Crime uses **nerve** and has risk/reward progression.

Early examples:

- Shoplift in Camden
- Steal an unlocked bicycle
- Pickpocket in Soho
- Break into a flat in Hackney

Crime results may affect:

- cash
- player XP
- crime XP
- district reputation
- wanted level
- health
- jail time
- hospital time
- items

### Crime Skills

Planned specialisations:

- Theft
- Burglary
- Fraud
- Vehicle Crime
- Robbery

Repeating related crimes develops the relevant skill and unlocks harder opportunities.

### Wanted Level

Wanted level increases through crime and falls over real time. Higher wanted levels increase police pressure and may restrict activities.

### Crime Chains and Heists

Later progression includes multi-stage crime chains and coordinated heists with roles such as driver, hacker, enforcer and inside man.

---

## Jobs and Legal Careers

Legal income is a full progression path.

Planned career families:

- Construction
- Hospitality
- Transport
- Technology
- Finance
- Security

Careers can include promotions, requirements, salary, work XP, district reputation and perks.

Quick side work may exist separately from long-term careers.

---

## Economy

Four layers:

1. Cash — carried and potentially vulnerable
2. Bank — protected funds
3. Assets — properties, vehicles, businesses and investments
4. Expenses — travel, gyms, items, repairs, fines, medical costs and upgrades

Money should always have competing uses such as training, equipment, vehicles, housing, businesses, banking and operations.

A future net-worth value can combine cash, bank funds, properties, vehicles, businesses and investments.

---

## Items, Shops and Inventory

Planned item categories:

- Consumables
- Weapons
- Armour
- Tools
- Electronics
- Vehicles
- Collectibles
- Quest items
- Materials

Items may come from shops, crimes, jobs, missions, events, rewards or player trading.

Shops belong to districts and can have individual stock and pricing.

### Item value

Every item has a `value`: the lowest price any shop charges for it. That is
the single source of truth for what an item is worth, and everything that
pays out for an item is a fraction of it.

### The black market

Legitimate shops sell but never buy — they do not take stolen goods. Selling
happens at a **fence**, one per district, which buys anything at **50% of
value**, or **65%** for the categories that fence deals in:

| Fence | District | Deals in |
| --- | --- | --- |
| Camden Lock Market | Camden | Boosts, medical |
| The Railway Arch | Brixton | Weapons |
| The Back Room | Soho | Medical, tools |
| Unit Nine | Shoreditch | Tools |
| The Towpath | Hackney | Weapons, armour |

Because value is the *cheapest* shop price and the best fence rate is 65%,
buying in one district and fencing in another is always a loss. Cross-district
arbitrage is closed by construction rather than by a rule, and a test pins it.

### Loot

A successful crime yields an item some of the time — 45% for the small Camden
jobs, up to 60% for the Hackney canal handover — from a pool suited to the
crime. A Camden shoplift yields whatever was by the till; the canal handover
yields the sort of kit somebody was moving for a reason.

Failed crimes drop nothing. When there is nowhere to put a drop — the bag is
full, or it is a second machete and only one may be carried — the fence price
is paid in cash instead, so a drop is never silently lost.

### The item market

Alongside the fence, a **global market** where players list what they are
selling at their own asking price, and anyone can buy from anywhere.

The two are deliberately a floor and a ceiling. The fence is instant,
guaranteed and poor value, and works with nobody else online. The market
pays better but needs a buyer to turn up. With a small population the fence
carries the economy; the market grows into relevance as the population does.

- Listing **escrows** the items out of the seller's inventory onto the
  listing. That is what makes selling the same machete twice impossible.
- The seller pays **5% commission** on a sale, so money leaves the economy
  on every trade. It also makes wash trading between two accounts a way to
  *destroy* money rather than launder it, so it needs no separate guard.
- Nothing may be listed below what the base fence rate would pay. Below
  that a seller should just walk to the black market, and it stops
  nominal-price listings being used to shuffle items between accounts.
  Because the floor is the *base* rate, a speciality fence can still beat
  a bottom-priced listing — the district fences stay worth walking to.
- A buyer who cannot carry the goods is refused outright, unlike loot,
  which pays cash instead. A purchase is deliberate and should fail
  loudly.
- Listings do not expire.

Loot lifts the safe early crimes by roughly 30–40%: a Camden shoplift goes
from about £188 to £241 an hour. It deliberately does **not** rescue the
high-tier crimes whose multi-day jail sentences dominate their rate — Soho
Nightclub moves from £12 to £18 an hour against the shoplift's £241, so the
safe crimes stay correct.

---

## Combat

Combat is turn-based and reusable for PvP and PvE.

Core flow:

1. Compare attacker Speed against defender Dexterity.
2. Determine whether the attack lands.
3. Calculate damage using Strength and weapon effects.
4. Reduce damage using Defence and armour.
5. Apply health loss.
6. Continue until a combat result is reached.

Defeated players are hospitalised rather than permanently killed.

Possible PvP outcomes later:

- attack
- mug
- hospitalise
- leave

New-player protection, cooldowns and reduced rewards for extreme power differences should prevent abuse.

---

## Gangs

Gangs are player-created organisations.

Possible ranks:

- Leader
- Deputy
- Lieutenant
- Member
- Recruit

Gang systems may include:

- shared bank
- member permissions
- gang XP and levels
- gang upgrades
- safe houses
- training rooms
- garages
- medical rooms
- operations rooms
- gang missions
- district influence
- rivalries
- coordinated operations

Players belong to one gang at a time.

District influence provides bonuses and opportunities but should not allow one gang to permanently lock other players out of content.

---

## NPC Factions

Factions are world-controlled organisations rather than player-created gangs.

Possible examples:

- Metropolitan Police
- City Financial Network
- Docklands Union
- Soho Nightlife Association
- East London Underground
- Private Security Consortium

Player reputation ranges from hostile to allied. Helping one faction may damage standing with another so players cannot trivially maximise every relationship.

---

## Properties and Businesses

### Properties

Properties can provide:

- storage
- recovery bonuses
- garages
- safes
- prestige
- upgrade slots

Possible upgrades include security, gym rooms, medical rooms, storage, garages and offices.

### Businesses

Businesses should be active investments rather than passive infinite-money generators.

Potential legal businesses:

- Cafe
- Garage
- Security company
- Construction company
- Logistics company
- Tech company
- Nightclub

Potential underground businesses may appear later.

Business systems can include:

- revenue
- wages
- operating costs
- staff
- reputation
- security
- marketing
- upgrades
- random events
- contracts

Player-owned businesses may eventually employ other players.

---

## Vehicles

Vehicles are useful game systems, not merely collectibles.

Core vehicle stats:

- class
- value
- speed
- handling
- reliability
- storage
- heat
- condition

Vehicles connect to:

- travel
- jobs
- delivery work
- crime
- getaway roles
- businesses
- garages
- gang operations

A future Driving skill can improve travel, pursuit performance, reliability and specialist work.

Later systems may include fuel, maintenance, modifications, vehicle heat, stolen vehicles, auctions and player trading.

---

## Offline Regeneration

Energy, nerve and health should regenerate using timestamps rather than background loops.

Example:

- store current energy and `last_energy_update`
- when the player returns, calculate elapsed time
- grant the appropriate recovered amount
- update the stored timestamp

The same principle applies to jail, hospital and travel timers.

Current rates and caps:

| Resource | Cap | Regeneration |
| --- | --- | --- |
| Energy | 150 | +5 every 10 minutes |
| Nerve | 20 | +1 every 5 minutes |
| Happiness | 100 | +5 every 15 minutes |
| Health | 100 + 10 per level | +5 every 15 minutes |

Because the stored timestamp is advanced to the last completed tick
boundary, the time elapsed since it is exactly the progress made towards
the next one. The HUD uses that to show, on each meter, how long until
the next tick and how long until the meter is full.

---

## Backend Architecture Rule

Game rules should return data rather than directly depending on `input()` or `print()` wherever practical.

For example, a crime engine should eventually return a structured result containing success, reward, damage, XP and wanted changes. The terminal UI can print that result today and a web application can render the same result later.

This separation allows the backend to survive the future transition to Flask/FastAPI and PostgreSQL.
