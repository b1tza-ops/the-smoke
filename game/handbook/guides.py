"""The guides.

Every number here is the one the game actually uses. When a constant
changes, this file changes with it -- `tests/gameplay/test_handbook.py`
checks the figures that are cheap to check automatically, and the rest
is on whoever edits the rule.
"""

from dataclasses import dataclass

from game.handbook.blocks import Bullets, Heading, Note, Steps, Table, Text


@dataclass(frozen=True)
class Guide:
    slug: str
    title: str
    summary: str
    section: str
    icon: str
    blocks: tuple


GUIDES = (
    # ------------------------------------------------ getting started
    Guide(
        slug="first-hour",
        title="Your First Hour",
        summary="What to do with £500 and no reputation.",
        section="Getting Started",
        icon="home",
        blocks=(
            Text(
                "You start in **Camden** with **£500**, a first aid kit, an "
                "energy drink, and nothing anyone would call a reputation. "
                "Here is the short version of what to do with it."
            ),
            Steps((
                "Commit a **Camden High Street shoplift** a few times. It "
                "costs 2 nerve, succeeds about 80% of the time, and pays "
                "£20–60. It is the safest thing in London.",
                "Join **Average Joe's Camden** for £100. It trains 20% "
                "harder than the free gym and pays that back quickly.",
                "Fight the **Market Runner** when you have energy spare. "
                "It costs 10 energy and pays £30–55 plus 15 XP.",
                "Put anything you are not about to spend in the "
                "[bank](/bank). Cash on you can be taken; cash in the "
                "bank cannot.",
                "At level 2, travel to **Soho** and look at the better "
                "gyms there.",
            )),
            Note(
                "Crime and fighting draw on different pools — nerve and "
                "energy — so you can do both at once. Doing only one is "
                "leaving half your income on the table.",
                tone="tip",
            ),
            Heading("What not to do"),
            Bullets((
                "Do not spend your last pound on a gym membership. Jail "
                "and hospital both cost time, not money, but being broke "
                "means you cannot buy your way out of a bad run.",
                "Do not attempt the **Hackney canal handover** because it "
                "pays £700–1,500. It succeeds 28% of the time and the "
                "failures cost you five days in jail.",
                "Do not buy a gun before level 7. They are only sold in "
                "Hackney, and Hackney needs level 7 to reach.",
            )),
        ),
    ),
    Guide(
        slug="energy-and-nerve",
        title="Energy, Nerve and Happiness",
        summary="The four clocks everything else runs on.",
        section="Getting Started",
        icon="energy",
        blocks=(
            Text(
                "Almost everything you do spends one of four pools. They "
                "all refill on their own, on their own schedule, whether "
                "you are logged in or not."
            ),
            Table(
                headers=("Pool", "Refills", "Per hour", "Spent on"),
                rows=(
                    ("Energy", "+5 every 10 minutes", "30", "Training, fighting"),
                    ("Nerve", "+1 every 5 minutes", "12", "Crime"),
                    ("Happiness", "+5 every 15 minutes", "20", "Training"),
                    ("Health", "+5 every 15 minutes", "20", "Recovering from fights"),
                ),
                caption="Regeneration is the same for everyone.",
            ),
            Note(
                "Hover any bar in the header to see exactly when the next "
                "point lands and when the pool will be full.",
                tone="tip",
            ),
            Heading("Nerve is the bottleneck"),
            Text(
                "At 12 nerve an hour, a 2-nerve shoplift is six an hour and "
                "a 12-nerve canal handover is one an hour. **Nerve is the "
                "scarcest thing you own** — spend it on the crime with the "
                "best return per nerve, not the biggest headline payout."
            ),
            Heading("Happiness is a multiplier, not a resource"),
            Text(
                "Training at full happiness gains **twice** what training "
                "at zero does. The multiplier slides smoothly between "
                "1.0 and 0.5 as happiness falls, and every train spends "
                "half a point of happiness per point of energy."
            ),
            Text(
                "In practice: train while happiness is high, and let it "
                "refill rather than grinding it into the floor. "
                "Fish and chips from any district shop restores 25."
            ),
        ),
    ),

    # --------------------------------------------------- making money
    Guide(
        slug="crime-and-jail",
        title="Crime and Jail",
        summary="What each job pays, and what it costs when it goes wrong.",
        section="Making Money",
        icon="crimes",
        blocks=(
            Text(
                "Crime is your main early income. Each job costs nerve, "
                "succeeds some of the time, and lands you in jail the rest."
            ),
            Table(
                headers=("Crime", "District", "Nerve", "Pays", "Success", "Jail if caught"),
                rows=(
                    ("Shoplift", "Camden", "2", "£20–60", "80%", "10%, 10 min"),
                    ("Market stall", "Camden", "4", "£60–140", "65%", "15%, 1 hour"),
                    ("Phone snatch", "Brixton", "3", "£40–100", "72%", "12%, 30 min"),
                    ("Warehouse", "Brixton", "7", "£180–480", "42%", "25%, 12 hours"),
                    ("Pickpocket", "Soho", "4", "£50–150", "65%", "15%, 30 min"),
                    ("Nightclub office", "Soho", "8", "£250–650", "38%", "30%, 3 days"),
                    ("Gallery lift", "Shoreditch", "6", "£180–420", "55%", "22%, 90 min"),
                    ("Server room", "Shoreditch", "10", "£400–900", "34%", "35%, 4 days"),
                    ("Canal lock-up", "Hackney", "9", "£350–750", "45%", "28%, 2 days"),
                    ("Canal handover", "Hackney", "12", "£700–1,500", "28%", "40%, 5 days"),
                ),
            ),
            Heading("The big jobs are worse than they look"),
            Text(
                "Read that table by the hour, not by the payout. A Camden "
                "shoplift is six an hour at 80%, which is roughly **£190 an "
                "hour**. The Soho nightclub office pays five times more per "
                "job — but at 8 nerve, 38% success and a **three-day** "
                "sentence, it works out around £12 an hour."
            ),
            Note(
                "Jail time is real time. A five-day sentence is five days "
                "in which you cannot commit crimes, train, fight or travel.",
                tone="warning",
            ),
            Heading("Loot"),
            Text(
                "Succeeding at a crime sometimes turns up an item as well "
                "as cash. If your pockets are full, or you already carry "
                "as many as you can hold, it is sold on the way and you "
                "get the cash instead — a drop is never lost."
            ),
        ),
    ),
    Guide(
        slug="selling-what-you-steal",
        title="Selling What You Steal",
        summary="The fence, the black market and the player market.",
        section="Making Money",
        icon="shop",
        blocks=(
            Text(
                "Ordinary shops sell but never buy. Nobody behind a legitimate "
                "counter is taking stolen goods off you. There are two other "
                "ways to turn an item into money."
            ),
            Heading("The fence — instant, and always there"),
            Text(
                "Every district has a **black market** fence. It buys "
                "anything at **50% of value**, or **65%** for the categories "
                "that fence deals in. It is the floor under every item you "
                "own, and it works whether or not anyone else is online."
            ),
            Table(
                headers=("Fence", "District", "Pays 65% for"),
                rows=(
                    ("Camden Lock Market", "Camden", "Boosts, medical"),
                    ("The Railway Arch", "Brixton", "Weapons"),
                    ("The Back Room", "Soho", "Medical, tools"),
                    ("Unit Nine", "Shoreditch", "Tools"),
                    ("The Towpath", "Hackney", "Weapons, armour"),
                ),
            ),
            Heading("The item market — better prices, needs a buyer"),
            Text(
                "The [item market](/market) lets you set your own asking "
                "price and wait. It pays far better than the fence when "
                "something sells, and nothing at all when it does not. A "
                "**5% commission** comes off every sale."
            ),
            Note(
                "Buying in one district and fencing in another is always a "
                "loss. An item's value is the cheapest price any shop "
                "charges for it, and the best fence rate is 65% of that.",
                tone="info",
            ),
        ),
    ),

    # ----------------------------------------------- getting stronger
    Guide(
        slug="the-gym",
        title="The Gym",
        summary="How training actually works, and which gym is worth it.",
        section="Getting Stronger",
        icon="gym",
        blocks=(
            Text(
                "Training converts energy into stats. What you gain from one "
                "train comes down to four things:"
            ),
            Bullets((
                "**Energy spent** — 5 at a lightweight gym, 10 at a "
                "middleweight, 25 at a heavyweight.",
                "**The gym's multiplier** for the stat you are training.",
                "**Your current stat** — gains rise with it, doubling at "
                "2,000, tripling at 4,000.",
                "**Your happiness** — full happiness trains twice as hard "
                "as empty.",
            )),
            Heading("Weight class is commitment, not efficiency"),
            Text(
                "A heavyweight gym is not more efficient per point of "
                "energy — it commits more energy, and proportionally more "
                "happiness, to each train. What it buys you is a bigger "
                "multiplier. Spending 100 energy gets you the same number "
                "of points whether you spend it in twenty small trains or "
                "four large ones."
            ),
            Heading("The ladder"),
            Table(
                headers=("Gym", "District", "Class", "Membership", "Level"),
                rows=(
                    ("Camden Community Gym", "Camden", "Light", "Free", "1"),
                    ("Average Joe's", "Camden", "Light", "£100", "1"),
                    ("Camden Ironworks", "Camden", "Light", "£250", "1"),
                    ("Brixton Barbell Club", "Brixton", "Light", "£500", "2"),
                    ("South London Performance", "Brixton", "Light", "£1,000", "2"),
                    ("Soho Fitness Rooms", "Soho", "Light", "£2,500", "2"),
                    ("West End Fight Lab", "Soho", "Middle", "£5,000", "3"),
                    ("London Elite", "Soho", "Middle", "£10,000", "4"),
                    ("The Warehouse", "Shoreditch", "Middle", "£25,000", "5"),
                    ("Iron Yard", "Shoreditch", "Middle", "£60,000", "6"),
                    ("The Arches", "Hackney", "Middle", "£150,000", "7"),
                    ("Marsh Athletic", "Hackney", "Heavy", "£400,000", "9"),
                    ("Powerhouse", "Hackney", "Heavy", "£1,000,000", "12"),
                    ("The Lock", "Hackney", "Heavy", "£2,500,000", "15"),
                ),
                caption="Membership is paid once and never expires.",
            ),
            Note(
                "Buy the next gym as soon as you can afford it without "
                "going broke. A membership is permanent and every train "
                "after it is worth more.",
                tone="tip",
            ),
        ),
    ),
    Guide(
        slug="fighting",
        title="Fighting",
        summary="Street opponents, other players, and what decides a fight.",
        section="Getting Stronger",
        icon="pvp",
        blocks=(
            Text(
                "Every fight costs **10 energy**. What you bring to it is "
                "your stats plus whatever you have equipped."
            ),
            Heading("Street opponents"),
            Table(
                headers=("Opponent", "District", "Pays", "XP", "Strength"),
                rows=(
                    ("Market Runner", "Camden", "£30–55", "15", "7"),
                    ("Canal Yard Enforcer", "Camden", "£70–125", "35", "13"),
                    ("Soho Door Enforcer", "Soho", "£250–400", "80", "25"),
                ),
            ),
            Text(
                "Street opponents are the steadiest income in the game. "
                "They cost energy rather than nerve, so they stack on top "
                "of everything you earn from crime."
            ),
            Heading("Player fights"),
            Text(
                "Attacking another player is rated and affects your "
                "standing on the [leaderboard](/pvp/leaderboard). Losing a "
                "fight puts you in hospital, where you can do nothing until "
                "you heal."
            ),
            Note(
                "An equipped gun with no ammunition contributes **nothing**. "
                "It sits in the slot marked inert and you fight as though "
                "unarmed. Check before you attack.",
                tone="warning",
            ),
        ),
    ),
    Guide(
        slug="guns-and-ammunition",
        title="Guns and Ammunition",
        summary="Where to buy a pistol, and why it needs feeding.",
        section="Getting Stronger",
        icon="guns",
        blocks=(
            Text(
                "Firearms are the strongest weapons in London and the only "
                "ones that cost money to keep using. They are sold at the "
                "**Kingsland Arms Bazaar** in Hackney and nowhere else, so "
                "owning one means reaching **level 7** first."
            ),
            Table(
                headers=("Pistol", "Strength", "Price", "Feeds on"),
                rows=(
                    ("Derringer .22", "+16", "£2,000", ".22 Rounds"),
                    ("Converted Blank Pistol", "+18", "£2,800", "9mm Rounds"),
                    ("Snub-Nose .38", "+20", "£3,600", ".38 Rounds"),
                    ("Compact 9mm", "+22", "£4,800", "9mm Rounds"),
                ),
            ),
            Table(
                headers=("Round", "Price each"),
                rows=(
                    (".22 Rounds", "£10"),
                    ("9mm Rounds", "£16"),
                    (".38 Rounds", "£20"),
                ),
                caption="One round is spent per fight.",
            ),
            Heading("Buy the calibre, not just the gun"),
            Text(
                "The **9mm** feeds two pistols — the Converted Blank Pistol "
                "and the Compact 9mm. Upgrading between them does not "
                "strand your rounds. The .22 and the .38 each feed one gun "
                "only."
            ),
            Note(
                "No rounds of the right calibre in your inventory means no "
                "strength bonus at all. You are never blocked from "
                "fighting — you just fight unarmed.",
                tone="warning",
            ),
        ),
    ),

    # -------------------------------------------------- around london
    Guide(
        slug="travel",
        title="Getting Around",
        summary="Walk, bus or Underground, and what each costs you.",
        section="Around London",
        icon="travel",
        blocks=(
            Text(
                "Crimes, gyms, shops and opponents are tied to districts, "
                "so moving around is part of playing. Every route offers "
                "three ways to make it."
            ),
            Table(
                headers=("Mode", "Fare", "Time"),
                rows=(
                    ("Walk", "Free", "Three times as long"),
                    ("Bus", "Standard", "Standard"),
                    ("Underground", "Double", "Half"),
                ),
            ),
            Bullets((
                "**Walking is free** and always available. If you are "
                "going to be away from the keyboard anyway, walk.",
                "**There is no Underground to Hackney.** Walk or take the "
                "bus.",
                "You cannot do anything else while travelling — no crime, "
                "no training, no fighting.",
            )),
            Heading("Where everything is"),
            Table(
                headers=("District", "Unlocks at", "Known for"),
                rows=(
                    ("Camden", "Level 1", "Safe crime, the first gyms"),
                    ("Brixton", "Level 1", "Weapons and hardware"),
                    ("Soho", "Level 2", "Nightlife, the casino, better gyms"),
                    ("Shoreditch", "Level 5", "Tools and electronics"),
                    ("Hackney", "Level 7", "Firearms, the heaviest gyms"),
                ),
            ),
            Note(
                "The [City](/city) page lists every place in London and "
                "tells you which ones need a journey.",
                tone="tip",
            ),
        ),
    ),
    Guide(
        slug="the-casino",
        title="The Casino",
        summary="Three tables, and honest odds on all of them.",
        section="Around London",
        icon="casino",
        blocks=(
            Text(
                "**The Golden Square** in Soho takes players from **level "
                "3**, with a stake ceiling of **£250 × your level**. The "
                "table maximum on any single payout is £500,000."
            ),
            Text(
                "Here is what each game returns over time. These are not "
                "estimates — they are computed from the paytables, and the "
                "test suite recomputes them on every change."
            ),
            Table(
                headers=("Game", "Returns", "House edge"),
                rows=(
                    ("Fruit Machines", "91.7%", "8.3%"),
                    ("Keno", "90–92%", "8–10%"),
                    ("Blackjack", "99.8%", "0.2%"),
                ),
                caption="Return to player over the long run.",
            ),
            Heading("Blackjack is the only good bet"),
            Text(
                "That is deliberate and it is how a real floor works. "
                "Slots and keno pay for the room; blackjack rewards anyone "
                "who learns basic strategy. The house rules are all the "
                "player-friendly ones: dealer stands on every 17, blackjack "
                "pays 3:2, doubling on any two cards including after a "
                "split, splitting up to four hands, and late surrender."
            ),
            Note(
                "A fresh shoe is dealt for every hand, so counting cards "
                "gets you nowhere. That is what makes the thin edge safe "
                "to offer.",
                tone="info",
            ),
            Note(
                "Over enough hands the house wins every one of these "
                "games. That is what a house edge means. Gamble with what "
                "you can afford to lose.",
                tone="warning",
            ),
        ),
    ),
    Guide(
        slug="the-loan-shark",
        title="The Loan Shark",
        summary="Ronnie Dell lends fast and collects harder.",
        section="Around London",
        icon="bank",
        blocks=(
            Text(
                "**Ronnie Dell** works out of the back of a Soho pub and "
                "will put money in your hand on a handshake. There is no "
                "credit check and no waiting. There is also no forgiveness."
            ),
            Heading("What he will lend"),
            Bullets((
                "From **level 3**. Below that he does not get out of bed.",
                "**£5,000 for every level you have**, so £50,000 at level "
                "10 and £100,000 at level 20.",
                "**£1,000 minimum.** He is not interested in pocket money.",
                "The ceiling counts what you already owe, so a £20,000 "
                "debt at level 10 leaves you £30,000 of room.",
            )),
            Heading("What it costs"),
            Text(
                "**2.5% of the principal per day**, charged by the second "
                "rather than in daily lumps — so paying early genuinely "
                "costs less. Your first payment is due **three days** "
                "after you borrow."
            ),
            Table(
                headers=("Borrowed", "After 1 day", "After 3 days"),
                rows=(
                    ("£5,000", "£125", "£375"),
                    ("£20,000", "£500", "£1,500"),
                    ("£50,000", "£1,250", "£3,750"),
                ),
                caption="Interest owed on top of the principal.",
            ),
            Heading("Paying him"),
            Bullets((
                "Payments clear the **interest first**, then the "
                "principal.",
                "A payment only counts as made if it **covers the "
                "interest**. Pay less and the clock keeps running.",
                "Covering the interest buys you another three days.",
                "You can pay **from anywhere in London** — you only have "
                "to be in Soho to borrow.",
                "Type more than you owe and he takes only what is owed.",
            )),
            Heading("Missing a payment"),
            Text(
                "Ronnie's people come and find you. You go to hospital, "
                "and **the debt stays exactly where it was** — you have "
                "lost the time and gained nothing. The stay gets longer "
                "every time it happens."
            ),
            Table(
                headers=("Missed", "Hospital"),
                rows=(
                    ("First", "30 minutes"),
                    ("Second", "2 hours"),
                    ("Third", "6 hours"),
                    ("Fourth or more", "12 hours"),
                ),
            ),
            Note(
                "Staying off his page does not help. The collection "
                "happens wherever you are, on whatever you are doing.",
                tone="warning",
            ),
            Note(
                "He remembers. Clearing a debt does not reset the missed "
                "payments, so a defaulter who borrows again picks up where "
                "they left off.",
                tone="info",
            ),
            Note(
                "Borrowing to gamble is how players lose accounts. The "
                "[casino](/forum/the-casino) keeps an edge on every game; "
                "Ronnie keeps one on you.",
                tone="warning",
            ),
        ),
    ),
)

GUIDES_BY_SLUG = {guide.slug: guide for guide in GUIDES}

# Section order on the index, which is roughly the order a new player
# meets them rather than alphabetical.
SECTION_ORDER = (
    "Getting Started",
    "Making Money",
    "Getting Stronger",
    "Around London",
)


def sections():
    """The guides grouped for the index."""
    return tuple(
        (name, tuple(g for g in GUIDES if g.section == name))
        for name in SECTION_ORDER
    )


def get_guide(slug):
    return GUIDES_BY_SLUG.get(slug)


def validate_catalogue():
    """Every guide is reachable, unique, and in a real section."""
    slugs = [guide.slug for guide in GUIDES]
    if len(slugs) != len(set(slugs)):
        raise ValueError("two guides share a slug")

    for guide in GUIDES:
        if guide.section not in SECTION_ORDER:
            raise ValueError(f"{guide.slug} is in unknown section {guide.section!r}")
        if not guide.blocks:
            raise ValueError(f"{guide.slug} has no content")


validate_catalogue()
