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

| District | Unlock | Identity |
| --- | ---: | --- |
| Camden | 1 | Markets, nightlife, beginner content |
| Brixton | 1 | Jobs, gyms, local gangs and street progression |
| Soho | 3 | Nightlife, tourism, pickpocketing and clubs |
| Shoreditch | 5 | Tech, nightlife and electronics |
| Hackney | 7 | Residential crime, garages and gang activity |
| The City | 10 | Finance, banking and investments |
| Canary Wharf | 12 | Corporate careers and expensive property |
| Chelsea | 15 | Luxury property and high-value opportunities |
| Westminster | 20 | Prestige, high security and advanced missions |

Districts contain their own crimes, jobs, gyms, shops, properties and reputation progression.

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
- energy cost
- stat multipliers
- specialization

This allows multiple gyms without hardcoding separate training logic for each one.

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

---

## Backend Architecture Rule

Game rules should return data rather than directly depending on `input()` or `print()` wherever practical.

For example, a crime engine should eventually return a structured result containing success, reward, damage, XP and wanted changes. The terminal UI can print that result today and a web application can render the same result later.

This separation allows the backend to survive the future transition to Flask/FastAPI and PostgreSQL.
