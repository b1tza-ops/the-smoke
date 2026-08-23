# The Smoke — Backend Roadmap

## Phase 1 — Foundation

- Registration and login
- Password hashing
- Persistent users and players
- Character creation/loading
- Health, energy, nerve and battle stats
- SQLite persistence
- Git feature-branch workflow

## Phase 2 — Core V1 Gameplay

- XP and level progression
- Offline health/energy/nerve regeneration
- Wanted level
- Jail and hospital timers
- Crime XP and basic crime progression
- 2–3 London districts
- District reputation
- Basic travel
- Multiple district-specialised gyms
- Starter housing (tent/hostel/council flat)
- One legal career path (London Construction)
- Banking
- Basic inventory/items

## Phase 3 — World Expansion

- More London districts
- Additional career paths
- Shops and district inventories
- Property progression
- Vehicles and driving skill
- Crime specialisations
- Crime chains
- Faction reputation

## Phase 4 — Combat and Social Systems

- Reusable combat engine
- PvE encounters
- Weapons and armour
- PvP protections
- Mugging/hospitalisation
- Gangs
- Gang upgrades
- Gang operations
- District influence

## Phase 5 — Wealth and Advanced Gameplay

- Businesses
- Employees and company progression
- Investments
- Vehicle upgrades/maintenance
- Advanced properties
- Player market
- Coordinated heists
- Advanced factions

## Phase 6 — Web Transition

After the backend rules and persistence are mature:

- Add Flask or FastAPI web layer
- Browser registration/login/session handling
- Dashboard and character pages
- Gym/crime/job/travel pages
- Replace terminal presentation while reusing core game modules
- Move from SQLite to PostgreSQL before serious multiplayer scale
- Deploy to VPS
- Domain, HTTPS and production configuration

## V1 Definition

V1 should be considered playable when a user can:

1. Register and log in.
2. Create and persist a character.
3. Recover resources over real time.
4. Train in more than one gym.
5. Commit multiple crimes and progress crime skill.
6. Gain XP/levels and unlock content.
7. Travel between at least three London districts.
8. Gain district reputation.
9. Work at least one legal career.
10. Use a bank and basic inventory.
11. Experience jail/hospital/wanted mechanics.
12. Begin with starter housing and progress to a better residence.

Features such as full PvP, businesses, player gangs, heists and a player-driven market are intentionally post-V1.
