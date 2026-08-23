# V1 playable backend acceptance review

This review maps the playable-backend definition of done to implemented,
persistent, and automated behaviour.

## Checklist

| Issue | System | Evidence |
| --- | --- | --- |
| #1 | Offline energy and nerve regeneration | Completed-tick, cap, repeated-load, and exact-boundary tests |
| #2 | Player XP and level progression | Threshold, multi-level, invalid-value, and persistence tests |
| #3 | Crime progression and rewards | Cash, XP, crime XP, reputation, failure, and district tests |
| #4 | Wanted, jail, and hospital | Decay, cap, expiry, persistence, and activity restrictions |
| #5 | London districts and travel | Cost, duration, arrival, restrictions, and persistence |
| #6 | Starting housing | Default tent, purchase rules, and persistence |
| #7 | Legal jobs | Three-hour shifts, pay, career XP, promotions, restrictions, and persistence |
| #8 | Bank and cash safety | Atomic deposits/withdrawals, rollback, ledger, and persistence |
| #9 | District gyms | Memberships, level/location rules, variable energy, multipliers, and persistence |
| #10 | Inventory | Starter items, categories, quantities, capacity, consumables, and persistence |
| #11 | Authentication hardening | bcrypt, hashed one-time tokens, expiry/reuse, generic recovery, and rate-limit hooks |
| #12 | Database migrations | Ordered, idempotent, rollback-safe SQLite migrations |
| #13 | Automated tests | One-command CI suite, isolated databases, and resource-boundary coverage |

## End-to-end journey

The V1 journey test creates an isolated fresh database and proves that a new
player can:

1. create an account and character;
2. begin in a tent with starter items;
3. join a legal career and finish a three-hour shift;
4. complete a crime and receive persistent rewards and wanted level;
5. train a battle stat with a chosen energy amount;
6. protect cash in the bank;
7. travel from Camden to Brixton;
8. consume medical and energy items;
9. save, reload, and retain the resulting state.

Run the full acceptance suite with:

    python3 -m unittest discover -s tests -v

## Merge order

The final V1 stack must be merged from oldest to newest:

1. #29 legal jobs
2. #30 district gyms
3. #31 starter inventory
4. #32 authentication hardening
5. #33 core test audit
6. the V1 acceptance PR

Each PR is independently reviewed by CI. Issue #14 should close only after the
full stack is merged into main.
