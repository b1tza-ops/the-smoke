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
        career_key,
        job_role_key,
        career_xp,
        shifts_completed,
        shift_started_at,
        shift_until,
        current_gym_key,
        happiness,
        max_happiness,
        last_happiness_update,
        max_health,
        last_health_update,
        travel_mode=None,
        crime_progress=None,
        district_reputation=None,
        unlocked_gyms=None,
        inventory=None,
        housing_suspended=False,
    ):

        # True while the rent is unpaid: the home is still theirs,
        # it simply stops doing anything for them until they settle.
        self.housing_suspended = housing_suspended
        self.id = player_id
        self.user_id = user_id
        self.name = name
        self.level = level
        self.money = money
        self.bank_balance = bank_balance
        self.current_district = current_district
        self.travel_destination = travel_destination
        self.travel_until = travel_until
        self.travel_mode = travel_mode
        self.residence_key = residence_key
        self.career_key = career_key
        self.job_role_key = job_role_key
        self.career_xp = career_xp
        self.shifts_completed = shifts_completed
        self.shift_started_at = shift_started_at
        self.shift_until = shift_until
        self.current_gym_key = current_gym_key
        self.unlocked_gyms = unlocked_gyms or {
            "camden_community"
        }
        self.inventory = inventory or {}
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
        self.happiness = happiness
        self.max_happiness = max_happiness
        self.last_happiness_update = last_happiness_update
        self.max_health = max_health
        self.last_health_update = last_health_update
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

        if self.job_role_key is None:
            print("Job: Unemployed")
        else:
            print(
                "Job:",
                self.job_role_key.replace("_", " ").title(),
            )
            print("Career XP:", self.career_xp)
            print("Shifts completed:", self.shifts_completed)

            if self.shift_until is not None:
                print("Shift finishes:", self.shift_until)

        print(
            "Gym:",
            self.current_gym_key.replace("_", " ").title(),
        )
        print("Inventory:", f"{len(self.inventory)}/20 slots")
        print(f"Health: {self.health}/{self.max_health}")
        print(f"Energy: {self.energy}/{self.max_energy}")
        print(f"Nerve: {self.nerve}/{self.max_nerve}")
        print(f"Happiness: {self.happiness}/{self.max_happiness}")
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
