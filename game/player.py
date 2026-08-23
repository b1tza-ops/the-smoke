from game.housing import get_residence


class Player:
    def __init__(
        self,
        player_id,
        user_id,
        name,
        level,
        money,
        health,
        energy,
        strength,
        defence,
        speed,
        dexterity,
        nerve,
        max_energy,
        max_nerve,
        last_energy_update,
        last_nerve_update,
        xp,
        wanted_level,
        last_wanted_update,
        jail_until,
        hospital_until,
        bank_balance,
        current_district,
        travel_destination,
        travel_until,
        residence_key,
        crime_progress=None,
        district_reputation=None,
    ):

        self.id = player_id
        self.user_id = user_id
        self.name = name
        self.level = level
        self.money = money
        self.bank_balance = bank_balance
        self.current_district = current_district
        self.travel_destination = travel_destination
        self.travel_until = travel_until
        self.residence_key = residence_key
        self.health = health
        self.energy = energy
        self.strength = strength
        self.defence = defence
        self.speed = speed
        self.dexterity = dexterity
        self.nerve = nerve
        self.max_energy = max_energy
        self.max_nerve = max_nerve
        self.last_energy_update = last_energy_update
        self.last_nerve_update = last_nerve_update
        self.xp = xp
        self.wanted_level = wanted_level
        self.last_wanted_update = last_wanted_update
        self.jail_until = jail_until
        self.hospital_until = hospital_until
        self.crime_progress = crime_progress or {}
        self.district_reputation = district_reputation or {}

    def show_stats(self):
        print("\n===== CHARACTER =====")
        print("Name:", self.name)
        print("Level:", self.level)
        print("XP:", self.xp)
        print("Cash:", self.money)
        print("Bank:", self.bank_balance)

        print(
            "Location:",
            self.current_district.title(),
        )

        if self.travel_destination is not None:
            print(
                "Travelling to:",
                self.travel_destination.title(),
            )
            print(
                "Arrival time:",
                self.travel_until,
            )

        residence = get_residence(self.residence_key)

        if residence is None:
            print("Residence:", self.residence_key)
        else:
            print("Residence:", residence.name)

        print("Health: ", self.health)
        print(f"Energy: {self.energy}/{self.max_energy}")
        print(f"Nerve: {self.nerve}/{self.max_nerve}")
        print(f"Wanted: {self.wanted_level}/100")

        if self.jail_until is not None:
            print("Status: In jail")
            print("Release time:", self.jail_until)

        elif self.hospital_until is not None:
            print("Status: In hospital")
            print("Discharge time:", self.hospital_until)

        else:
            print("Status: Free")

        print("\n===== BATTLE STATS =====")

        print("Strength:", self.strength)
        print("Defence:", self.defence)
        print("Speed:", self.speed)
        print("Dexterity:", self.dexterity)
