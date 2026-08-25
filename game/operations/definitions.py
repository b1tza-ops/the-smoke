"""The debt campaign: a chain of operations, one district at a time.

Each operation offers the same three-way choice -- persuasion, stealth or
force -- so a player can lean on whichever stat they have been training.
The approach they pick decides the cost, the wait, the trail they leave
and how much of the debt it clears.

Operation one is the Camden Collection the prologue always ran. Its
approach keys are preserved exactly, because completed accounts store
them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Approach:
    key: str
    name: str
    style: str
    description: str
    stat: str
    required_stat: int
    energy: int
    nerve: int
    duration_seconds: int
    paydown: int
    cash: int
    xp: int
    wanted: int
    risk: str
    outcome: str


@dataclass(frozen=True)
class Operation:
    key: str
    name: str
    district: str
    required_level: int
    summary: str
    briefing: str
    approaches: tuple[Approach, ...]
    clears_debt: bool = False

    def approach_for(self, key):
        for approach in self.approaches:
            if approach.key == key:
                return approach

        return None

    @property
    def approaches_by_key(self):
        return {
            approach.key: approach
            for approach in self.approaches
        }


CAMPAIGN = (
    Operation(
        key="camden_collection",
        name="The Camden Collection",
        district="camden",
        required_level=1,
        summary="Recover a debt ledger from an office above Camden High Street.",
        briefing=(
            "Your first contact needs a debt ledger recovered from an "
            "office above Camden High Street. How you retrieve it will "
            "shape what London learns about you."
        ),
        approaches=(
            Approach(
                key="talk_your_way_in",
                name="Talk your way in",
                style="Persuasion",
                description=(
                    "Pose as a courier, read the room and get the ledger "
                    "without a scene."
                ),
                stat="dexterity",
                required_stat=8,
                energy=5,
                nerve=3,
                duration_seconds=60,
                paydown=300,
                cash=80,
                xp=30,
                wanted=0,
                risk="Low",
                outcome=(
                    "The receptionist remembered your smile, not your "
                    "name. The ledger is yours and nobody raised the "
                    "alarm."
                ),
            ),
            Approach(
                key="slip_through_back",
                name="Slip through the back",
                style="Stealth",
                description=(
                    "Use the service alley, avoid the cameras and lift "
                    "the ledger quietly."
                ),
                stat="speed",
                required_stat=10,
                energy=8,
                nerve=5,
                duration_seconds=90,
                paydown=425,
                cash=120,
                xp=40,
                wanted=1,
                risk="Medium",
                outcome=(
                    "A camera caught only a hood and a blur. You escaped "
                    "with the ledger before anyone checked the office."
                ),
            ),
            Approach(
                key="force_the_door",
                name="Force the door",
                style="Force",
                description=(
                    "Move fast, break the lock and accept that Camden "
                    "will hear about it."
                ),
                stat="strength",
                required_stat=10,
                energy=12,
                nerve=7,
                duration_seconds=120,
                paydown=550,
                cash=180,
                xp=55,
                wanted=5,
                risk="High",
                outcome=(
                    "The door gave way and so did the guard. You have "
                    "the ledger, but sirens carried your name across "
                    "Camden."
                ),
            ),
        ),
    ),
    Operation(
        key="soho_favour",
        name="A Favour in Soho",
        district="soho",
        required_level=3,
        summary="Retrieve a members' book from a private club off Old Compton Street.",
        briefing=(
            "The ledger named a members' club off Old Compton Street. "
            "Your contact wants its book -- the one that lists who owes "
            "what to whom. The club keeps it behind the bar and keeps "
            "the bar staffed."
        ),
        approaches=(
            Approach(
                key="work_the_cloakroom",
                name="Work the cloakroom",
                style="Persuasion",
                description=(
                    "Take a shift on the door, learn the rota and walk "
                    "the book out in a coat."
                ),
                stat="dexterity",
                required_stat=13,
                energy=15,
                nerve=5,
                duration_seconds=300,
                paydown=250,
                cash=250,
                xp=80,
                wanted=0,
                risk="Low",
                outcome=(
                    "You hung coats for six hours and left with one that "
                    "was heavier than it came in. Nobody in Soho has any "
                    "idea your name was on the rota."
                ),
            ),
            Approach(
                key="roof_and_skylight",
                name="Over the rooftops",
                style="Stealth",
                description=(
                    "Cross three roofs, drop through the skylight and be "
                    "gone before last orders."
                ),
                stat="speed",
                required_stat=15,
                energy=22,
                nerve=7,
                duration_seconds=480,
                paydown=325,
                cash=380,
                xp=110,
                wanted=2,
                risk="Medium",
                outcome=(
                    "Old Compton Street never looked up. You were back "
                    "on the pavement with the book before the DJ changed "
                    "records."
                ),
            ),
            Approach(
                key="walk_in_loud",
                name="Walk in loud",
                style="Force",
                description=(
                    "Straight through the front, take the book off the "
                    "bar and let Soho draw its own conclusions."
                ),
                stat="strength",
                required_stat=15,
                energy=30,
                nerve=9,
                duration_seconds=600,
                paydown=400,
                cash=520,
                xp=140,
                wanted=8,
                risk="High",
                outcome=(
                    "Two doormen will be eating through a straw for a "
                    "month. You have the book, and Soho has a very clear "
                    "description of you."
                ),
            ),
        ),
    ),
    Operation(
        key="brixton_warehouse",
        name="The Brixton Warehouse",
        district="brixton",
        required_level=5,
        summary="Empty a container of stock a rival crew has been sitting on.",
        briefing=(
            "The book pointed at a railway arch in Brixton and a "
            "container that has not moved in eight months. Your contact "
            "wants what is in it before the crew sitting on it works out "
            "why the book went missing."
        ),
        approaches=(
            Approach(
                key="count_the_stock",
                name="Count the stock",
                style="Persuasion",
                description=(
                    "Arrive with a clipboard, an audit and enough "
                    "paperwork that nobody wants to read it."
                ),
                stat="dexterity",
                required_stat=18,
                energy=30,
                nerve=7,
                duration_seconds=900,
                paydown=275,
                cash=700,
                xp=210,
                wanted=1,
                risk="Low",
                outcome=(
                    "You signed for it in a name that does not exist and "
                    "they helped you load the van. The clipboard is "
                    "still the best tool anyone ever gave you."
                ),
            ),
            Approach(
                key="night_shift",
                name="Take the shift change",
                style="Stealth",
                description=(
                    "Eleven minutes between crews. Everything has to "
                    "happen inside them."
                ),
                stat="speed",
                required_stat=20,
                energy=42,
                nerve=9,
                duration_seconds=1200,
                paydown=375,
                cash=980,
                xp=280,
                wanted=4,
                risk="Medium",
                outcome=(
                    "The relief crew clocked on to a container that was "
                    "lighter than the one their mates clocked off from. "
                    "It took them two days to admit it."
                ),
            ),
            Approach(
                key="crowbar_and_nerve",
                name="Crowbar and nerve",
                style="Force",
                description=(
                    "Cut the lock, load the van and be past Loughborough "
                    "Junction before anyone finishes shouting."
                ),
                stat="strength",
                required_stat=20,
                energy=55,
                nerve=11,
                duration_seconds=1500,
                paydown=475,
                cash=1350,
                xp=350,
                wanted=12,
                risk="High",
                outcome=(
                    "The arch is a mess and one of them got the "
                    "registration. You have the stock, and a rival crew "
                    "now has a very specific grudge."
                ),
            ),
        ),
    ),
    Operation(
        key="camden_lockup",
        name="The Camden Lockup",
        district="camden",
        required_level=8,
        summary="Somebody else is collecting on your contact's patch. Find out who.",
        briefing=(
            "Someone has been collecting on your contact's patch using "
            "your contact's name, and running it out of a lockup behind "
            "the canal. Your contact would like the takings back and the "
            "arrangement ended."
        ),
        approaches=(
            Approach(
                key="buy_the_list",
                name="Buy the list",
                style="Persuasion",
                description=(
                    "Find the runner who keeps the round, and make him a "
                    "better offer than fear."
                ),
                stat="dexterity",
                required_stat=24,
                energy=45,
                nerve=9,
                duration_seconds=1800,
                paydown=300,
                cash=1600,
                xp=470,
                wanted=2,
                risk="Low",
                outcome=(
                    "He gave you the round, the takings and a name, and "
                    "he did it for less than the beating he was "
                    "expecting. Everyone has a number."
                ),
            ),
            Approach(
                key="wait_by_the_canal",
                name="Wait by the canal",
                style="Stealth",
                description=(
                    "Learn the collection round, then be inside the "
                    "lockup when the week's takings arrive."
                ),
                stat="speed",
                required_stat=26,
                energy=60,
                nerve=11,
                duration_seconds=2400,
                paydown=400,
                cash=2200,
                xp=600,
                wanted=6,
                risk="Medium",
                outcome=(
                    "They carried the week's takings in and set them "
                    "down a metre from where you were standing. You let "
                    "them leave before you did."
                ),
            ),
            Approach(
                key="end_the_arrangement",
                name="End the arrangement",
                style="Force",
                description=(
                    "Take the lockup, the takings and the argument, all "
                    "in one evening."
                ),
                stat="strength",
                required_stat=26,
                energy=75,
                nerve=13,
                duration_seconds=3000,
                paydown=500,
                cash=3000,
                xp=750,
                wanted=18,
                risk="High",
                outcome=(
                    "The arrangement is over and so is the lockup. Two "
                    "of them will not be collecting for anyone again, "
                    "and Camden watched you walk away from it."
                ),
            ),
        ),
    ),
    Operation(
        key="clearing_the_ledger",
        name="Clearing the Ledger",
        district="soho",
        required_level=12,
        summary="Settle the debt with the man who holds it. However it has to be settled.",
        briefing=(
            "Your contact was never the one you owed. The ledger, the "
            "book and the lockup all end at the same table in a Soho "
            "basement, and the man sitting at it has been waiting for "
            "you to be worth talking to. Whatever is left of your debt "
            "ends tonight."
        ),
        clears_debt=True,
        approaches=(
            Approach(
                key="settle_in_writing",
                name="Settle in writing",
                style="Persuasion",
                description=(
                    "You have his ledger, his book and his lockup. Put "
                    "all three on the table and negotiate."
                ),
                stat="dexterity",
                required_stat=30,
                energy=60,
                nerve=12,
                duration_seconds=3600,
                paydown=0,
                cash=4200,
                xp=1050,
                wanted=0,
                risk="Low",
                outcome=(
                    "He read all three, poured you a drink, and drew a "
                    "line through your name himself. You leave Soho "
                    "owing nothing and known to everyone worth knowing."
                ),
            ),
            Approach(
                key="take_the_basement",
                name="Take the basement quietly",
                style="Stealth",
                description=(
                    "Be in the room before he is, and be holding the "
                    "book of names when he arrives."
                ),
                stat="speed",
                required_stat=32,
                energy=80,
                nerve=14,
                duration_seconds=4500,
                paydown=0,
                cash=5800,
                xp=1300,
                wanted=10,
                risk="Medium",
                outcome=(
                    "He came down the stairs to find his own ledger open "
                    "at your page and you holding the pen. The debt died "
                    "with the conversation."
                ),
            ),
            Approach(
                key="burn_the_book",
                name="Burn the book",
                style="Force",
                description=(
                    "Every name in that basement owes him. Take the "
                    "book, and take the room with it."
                ),
                stat="strength",
                required_stat=32,
                energy=100,
                nerve=16,
                duration_seconds=5400,
                paydown=0,
                cash=7600,
                xp=1600,
                wanted=30,
                risk="High",
                outcome=(
                    "There is no ledger left to owe anything to. Half of "
                    "Soho is quietly grateful and the other half is "
                    "quietly furious, and both halves know exactly who "
                    "did it."
                ),
            ),
        ),
    ),
)

OPERATIONS_BY_KEY = {
    operation.key: operation
    for operation in CAMPAIGN
}

FIRST_OPERATION_KEY = CAMPAIGN[0].key


def get_operation(key):
    return OPERATIONS_BY_KEY.get(key)
