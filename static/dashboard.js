(() => {
    "use strict";

    const app = document.getElementById("gameApp");

    if (!app) {
        return;
    }

    const number = (value, fallback = 0) => {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    };

    const clamp = (value, minimum, maximum) => (
        Math.max(minimum, Math.min(maximum, value))
    );

    const parseServerTimestamp = (value) => {
        if (!value) {
            return null;
        }

        const parsed = Date.parse(value.replace(" ", "T") + "Z");
        return Number.isFinite(parsed) ? parsed : null;
    };

    const initialInventory = [
        {
            id: "first-aid",
            name: "First aid kit",
            type: "medical",
            icon: "✚",
            description: "Restores 25 health.",
            quantity: 2,
            action: "Use",
        },
        {
            id: "energy-tea",
            name: "Strong tea",
            type: "boost",
            icon: "☕",
            description: "Restores 20 energy.",
            quantity: 1,
            action: "Drink",
        },
        {
            id: "crowbar",
            name: "Steel crowbar",
            type: "weapon",
            icon: "⌁",
            description: "A crude close-range weapon.",
            quantity: 1,
            action: "Equip",
        },
        {
            id: "hoodie",
            name: "Armoured hoodie",
            type: "armour",
            icon: "◈",
            description: "Light protection without attention.",
            quantity: 1,
            action: "Equip",
        },
        {
            id: "burner",
            name: "Burner phone",
            type: "utility",
            icon: "▣",
            description: "Useful for underworld contacts.",
            quantity: 1,
            action: "Keep",
        },
    ];

    const crimes = [
        {
            id: "camden-shopleft",
            district: "Camden",
            name: "Shoplift on Camden High Street",
            description: "Pocket small goods while the staff are distracted.",
            nerve: 2,
            chance: 80,
            reward: [20, 60],
            xp: 10,
            wanted: 1,
            jailChance: 10,
            hospitalChance: 5,
            restrictionSeconds: 60,
        },
        {
            id: "camden-market",
            district: "Camden",
            name: "Rob a market stall",
            description: "Take the weekend takings before the owner notices.",
            nerve: 4,
            chance: 65,
            reward: [60, 140],
            xp: 25,
            wanted: 2,
            jailChance: 15,
            hospitalChance: 8,
            restrictionSeconds: 120,
        },
        {
            id: "brixton-phone",
            district: "Brixton",
            name: "Snatch a phone",
            description: "Move quickly through the crowd and disappear.",
            nerve: 3,
            chance: 72,
            reward: [40, 90],
            xp: 15,
            wanted: 2,
            jailChance: 12,
            hospitalChance: 8,
            restrictionSeconds: 90,
        },
        {
            id: "brixton-warehouse",
            district: "Brixton",
            name: "Break into a warehouse",
            description: "High-value stock, guards and very little room for error.",
            nerve: 7,
            chance: 43,
            reward: [180, 480],
            xp: 55,
            wanted: 5,
            jailChance: 25,
            hospitalChance: 20,
            restrictionSeconds: 300,
        },
        {
            id: "soho-pickpocket",
            district: "Soho",
            name: "Pickpocket in Soho",
            description: "Tourists, crowds and wallets everywhere.",
            nerve: 4,
            chance: 65,
            reward: [50, 150],
            xp: 25,
            wanted: 2,
            jailChance: 15,
            hospitalChance: 8,
            restrictionSeconds: 120,
        },
        {
            id: "soho-nightclub",
            district: "Soho",
            name: "Raid a nightclub office",
            description: "Get past security and take the manager's cash box.",
            nerve: 8,
            chance: 38,
            reward: [250, 650],
            xp: 65,
            wanted: 6,
            jailChance: 30,
            hospitalChance: 25,
            restrictionSeconds: 420,
        },
    ];

    const GYM_ENERGY_PER_TRAIN = 10;
    const GYM_GAIN_PER_TRAIN = 2;
    const DEFAULT_TRAINING_SETS = 1;

    const trainingOptions = [
        { stat: "strength", title: "Strength", description: "Increase raw striking power.", colour: "#ff7a45" },
        { stat: "defence", title: "Defence", description: "Take less damage in combat.", colour: "#49cce3" },
        { stat: "speed", title: "Speed", description: "Act before your opponent.", colour: "#b9f34b" },
        { stat: "dexterity", title: "Dexterity", description: "Improve accuracy and evasion.", colour: "#a98cff" },
    ];

    const jobs = [
        { id: "courier", title: "Bicycle courier", company: "Camden Dispatch", level: 1, energy: 8, pay: 45, xp: 8, description: "Deliver parcels through central London." },
        { id: "bartender", title: "Night bartender", company: "Soho Social", level: 2, energy: 10, pay: 80, xp: 12, description: "Work the late shift and learn who is who." },
        { id: "security", title: "Venue security", company: "Brixton Events", level: 4, energy: 12, pay: 130, xp: 18, description: "Keep order at busy music venues." },
        { id: "mechanic", title: "Garage mechanic", company: "East End Motors", level: 6, energy: 14, pay: 190, xp: 25, description: "Repair vehicles and make useful contacts." },
    ];

    const JOB_SHIFT_HOURS = 3;
    const JOB_SHIFT_DURATION_MS = JOB_SHIFT_HOURS * 60 * 60 * 1000;

    const dailyObjectives = [
        { key: "training", title: "Put in the work", description: "Complete 2 gym sessions", target: 2, icon: "◆" },
        { key: "crimes", title: "Make your mark", description: "Attempt 2 crimes", target: 2, icon: "!" },
        { key: "shifts", title: "Earn an honest wage", description: "Complete 1 work shift", target: 1, icon: "£" },
    ];

    const dailyReward = { cash: 250, xp: 30 };

    const localDateKey = (date = new Date()) => [
        date.getFullYear(),
        String(date.getMonth() + 1).padStart(2, "0"),
        String(date.getDate()).padStart(2, "0"),
    ].join("-");

    const createDailyState = () => ({
        date: localDateKey(),
        progress: Object.fromEntries(dailyObjectives.map((objective) => [objective.key, 0])),
        rewardClaimed: false,
    });

    const districts = {
        Camden: {
            description: "Markets, railway arches and a steady flow of low-risk opportunities.",
            risk: "Low",
            speciality: "Starter crimes",
            venue: "Ironworks Gym",
        },
        Soho: {
            description: "Nightlife, tourists and serious cash—watched closely by police and private security.",
            risk: "High",
            speciality: "Casino and nightlife",
            venue: "Lucky Shot Casino",
        },
        Brixton: {
            description: "Busy streets, warehouses and crews who notice unfamiliar faces.",
            risk: "Medium",
            speciality: "Street territory",
            venue: "Brixton Market",
        },
    };

    const createInitialState = () => {
        const hospitalUntil = parseServerTimestamp(app.dataset.hospitalUntil);
        const jailUntil = parseServerTimestamp(app.dataset.jailUntil);
        let restriction = null;

        if (hospitalUntil && hospitalUntil > Date.now()) {
            restriction = { kind: "hospital", until: hospitalUntil };
        } else if (jailUntil && jailUntil > Date.now()) {
            restriction = { kind: "jail", until: jailUntil };
        }

        return {
            version: 2,
            name: app.dataset.playerName || "Player",
            level: number(app.dataset.level, 1),
            xp: number(app.dataset.xp),
            nextLevelXp: number(app.dataset.nextLevelXp, 100),
            money: number(app.dataset.startingMoney, 500),
            health: number(app.dataset.health, 100),
            energy: number(app.dataset.energy, 100),
            maxEnergy: number(app.dataset.maxEnergy, 100),
            nerve: number(app.dataset.nerve, 20),
            maxNerve: number(app.dataset.maxNerve, 20),
            wanted: number(app.dataset.wanted),
            strength: number(app.dataset.strength, 10),
            defence: number(app.dataset.defence, 10),
            speed: number(app.dataset.speed, 10),
            dexterity: number(app.dataset.dexterity, 10),
            district: "Camden",
            activeJob: null,
            workShift: null,
            equipped: { weapon: null, armour: null },
            inventory: initialInventory.map((item) => ({ ...item })),
            activities: [
                { message: "Frontend prototype ready", time: Date.now() },
                { message: "Offline resources restored", time: Date.now() - 60000 },
            ],
            restriction,
            selectedBet: 10,
            daily: createDailyState(),
        };
    };

    const storageKey = `the-smoke-ui-v2:${app.dataset.playerId || "guest"}`;
    const initialState = createInitialState();

    const loadState = () => {
        try {
            const stored = JSON.parse(localStorage.getItem(storageKey));

            if (!stored || stored.version !== initialState.version) {
                return initialState;
            }

            const storedDaily = stored.daily?.date === initialState.daily.date
                ? stored.daily
                : initialState.daily;

            return {
                ...initialState,
                ...stored,
                name: initialState.name,
                maxEnergy: initialState.maxEnergy,
                maxNerve: initialState.maxNerve,
                inventory: Array.isArray(stored.inventory)
                    ? stored.inventory
                    : initialInventory.map((item) => ({ ...item })),
                equipped: { ...initialState.equipped, ...(stored.equipped || {}) },
                restriction: initialState.restriction || stored.restriction || null,
                workShift: stored.workShift
                    && jobs.some((job) => job.id === stored.workShift.jobId)
                    && Number.isFinite(Number(stored.workShift.completesAt))
                    ? {
                        ...stored.workShift,
                        startedAt: number(
                            stored.workShift.startedAt,
                            Number(stored.workShift.completesAt) - JOB_SHIFT_DURATION_MS,
                        ),
                        completesAt: Number(stored.workShift.completesAt),
                    }
                    : null,
                daily: {
                    ...initialState.daily,
                    ...storedDaily,
                    progress: {
                        ...initialState.daily.progress,
                        ...(storedDaily.progress || {}),
                    },
                },
            };
        } catch (error) {
            console.warn("Could not load frontend prototype state.", error);
            return initialState;
        }
    };

    let state = loadState();
    let activeCrimeFilter = "All";
    let activeInventoryFilter = "All";
    let selectedDistrict = state.district;
    let spinning = false;
    const trainingSets = Object.fromEntries(
        trainingOptions.map((option) => [option.stat, DEFAULT_TRAINING_SETS]),
    );
    let lastTrainingResult = null;

    const formatMoney = (value) => new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency: "GBP",
        maximumFractionDigits: 0,
    }).format(value);

    const randomBetween = (minimum, maximum) => (
        Math.floor(Math.random() * (maximum - minimum + 1)) + minimum
    );

    const saveState = () => {
        localStorage.setItem(storageKey, JSON.stringify(state));
    };

    const addActivity = (message) => {
        state.activities.unshift({ message, time: Date.now() });
        state.activities = state.activities.slice(0, 12);
    };

    const advanceDailyObjective = (key, amount = 1) => {
        const objective = dailyObjectives.find((item) => item.key === key);

        if (!objective || state.daily.rewardClaimed) {
            return;
        }

        const previous = number(state.daily.progress[key]);
        state.daily.progress[key] = clamp(previous + amount, 0, objective.target);

        if (previous < objective.target && state.daily.progress[key] === objective.target) {
            toast(`Daily objective complete · ${objective.title}`);
        }
    };

    const completedDailyObjectives = () => dailyObjectives.filter(
        (objective) => number(state.daily.progress[objective.key]) >= objective.target,
    ).length;

    const toast = (message, danger = false) => {
        const region = document.getElementById("toastRegion");
        const notification = document.createElement("div");
        notification.className = `toast${danger ? " toast--danger" : ""}`;
        notification.setAttribute("role", danger ? "alert" : "status");

        const copy = document.createElement("span");
        copy.textContent = message;
        notification.append(copy);
        region.append(notification);

        window.setTimeout(() => notification.remove(), 3200);
    };

    const timeAgo = (timestamp) => {
        const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));

        if (seconds < 10) return "just now";
        if (seconds < 60) return `${seconds}s ago`;
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return `${minutes}m ago`;
        return `${Math.floor(minutes / 60)}h ago`;
    };

    const formatShiftDuration = (milliseconds) => {
        const totalSeconds = Math.max(0, Math.ceil(milliseconds / 1000));
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;

        if (hours > 0) {
            return `${hours}h ${String(minutes).padStart(2, "0")}m`;
        }

        return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
    };

    const setBoundText = (name, value) => {
        document.querySelectorAll(`[data-bind="${name}"]`).forEach((element) => {
            element.textContent = value;
        });
    };

    const setMeter = (name, value) => {
        document.querySelectorAll(`[data-meter="${name}"]`).forEach((meter) => {
            meter.style.width = `${clamp(value, 0, 100)}%`;
        });
    };

    const setMovementStatus = (kind = null) => {
        const statusItem = document.getElementById("travelStatusItem");
        const status = document.getElementById("travelStatus");

        statusItem.dataset.state = kind || "free";
        status.textContent = kind === "hospital"
            ? "In hospital"
            : kind === "jail"
                ? "In jail"
                : "Free to travel";
    };

    const updateRestriction = () => {
        const banner = document.getElementById("restrictionBanner");

        if (!state.restriction) {
            banner.hidden = true;
            setMovementStatus();
            return false;
        }

        const remaining = Math.max(0, Math.ceil((state.restriction.until - Date.now()) / 1000));

        if (remaining <= 0) {
            const oldKind = state.restriction.kind;
            state.restriction = null;
            banner.hidden = true;
            addActivity(oldKind === "jail" ? "Released from jail" : "Discharged from hospital");
            toast(oldKind === "jail" ? "You have been released." : "You have been discharged.");
            saveState();
            renderAll();
            return false;
        }

        const hours = Math.floor(remaining / 3600);
        const minutes = Math.floor((remaining % 3600) / 60);
        const seconds = remaining % 60;
        const countdown = hours > 0
            ? `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
            : `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;

        const hospital = state.restriction.kind === "hospital";
        setMovementStatus(hospital ? "hospital" : "jail");
        banner.hidden = false;
        banner.classList.toggle("restriction-banner--hospital", hospital);
        document.getElementById("restrictionTitle").textContent = hospital ? "Recovering in hospital" : "Currently in jail";
        document.getElementById("restrictionMessage").textContent = hospital
            ? "Training, crimes and work are unavailable until discharge."
            : "You cannot train, work or commit crimes until release.";
        document.getElementById("restrictionCountdown").textContent = countdown;
        return true;
    };

    const canPerformAction = () => {
        if (!updateRestriction()) {
            return true;
        }

        toast(
            state.restriction.kind === "jail"
                ? "You cannot do that while in jail."
                : "You need to recover in hospital first.",
            true,
        );
        return false;
    };

    const updateCoreUI = () => {
        setBoundText("name", state.name);
        setBoundText("level", state.level);
        setBoundText("xp", state.xp);
        setBoundText("nextLevelXp", state.nextLevelXp);
        setBoundText("health", state.health);
        setBoundText("energy", state.energy);
        setBoundText("maxEnergy", state.maxEnergy);
        setBoundText("nerve", state.nerve);
        setBoundText("maxNerve", state.maxNerve);
        setBoundText("wanted", state.wanted);

        document.querySelectorAll("[data-money]").forEach((element) => {
            element.textContent = formatMoney(state.money);
        });

        document.querySelectorAll("[data-player-initial]").forEach((element) => {
            element.textContent = state.name.trim().charAt(0).toUpperCase() || "P";
        });

        setMeter("health", state.health);
        setMeter("energy", (state.energy / state.maxEnergy) * 100);
        setMeter("nerve", (state.nerve / state.maxNerve) * 100);
        setMeter("wanted", state.wanted);
        setMeter("xp", (state.xp / state.nextLevelXp) * 100);

        const wantedLabel = state.wanted === 0
            ? "Unknown to police"
            : state.wanted < 25
                ? "Police interest is low"
                : state.wanted < 60
                    ? "Actively investigated"
                    : "Major police target";
        document.querySelectorAll("[data-wanted-label]").forEach((element) => {
            element.textContent = wantedLabel;
        });

        document.getElementById("currentDistrict").textContent = state.district;
        document.getElementById("characterDistrict").textContent = state.district;
        document.getElementById("characterJob").textContent = state.activeJob
            ? jobs.find((job) => job.id === state.activeJob)?.title || "Employed"
            : "Unemployed";
    };

    const renderDailyObjectives = () => {
        if (state.daily.date !== localDateKey()) {
            state.daily = createDailyState();
            addActivity("New daily objectives available");
            saveState();
        }

        const list = document.getElementById("dailyObjectiveList");
        const completeCount = completedDailyObjectives();
        const allComplete = completeCount === dailyObjectives.length;

        list.innerHTML = dailyObjectives.map((objective) => {
            const progress = clamp(number(state.daily.progress[objective.key]), 0, objective.target);
            const complete = progress >= objective.target;
            const progressPercent = (progress / objective.target) * 100;

            return `
                <article class="daily-objective${complete ? " is-complete" : ""}">
                    <span class="daily-objective__icon" aria-hidden="true">${complete ? "✓" : objective.icon}</span>
                    <div class="daily-objective__copy">
                        <strong>${objective.title}</strong>
                        <small>${objective.description}</small>
                        <div class="meter meter--thin" aria-label="${objective.title}: ${progress} of ${objective.target}">
                            <span class="meter__fill" style="width:${progressPercent}%"></span>
                        </div>
                    </div>
                    <span class="daily-objective__count">${progress}/${objective.target}</span>
                </article>
            `;
        }).join("");

        document.getElementById("dailyProgressLabel").textContent = state.daily.rewardClaimed
            ? "Reward collected"
            : `${completeCount} / ${dailyObjectives.length} complete`;

        const claimButton = document.getElementById("claimDailyReward");
        claimButton.disabled = !allComplete || state.daily.rewardClaimed;
        claimButton.textContent = state.daily.rewardClaimed
            ? "Reward claimed"
            : allComplete
                ? `Claim ${formatMoney(dailyReward.cash)} + ${dailyReward.xp} XP`
                : "Complete all objectives";
    };

    const renderActivity = () => {
        const list = document.getElementById("activityList");
        list.replaceChildren();

        if (!state.activities.length) {
            const item = document.createElement("li");
            item.className = "activity-list-empty";
            item.textContent = "Your recent actions will appear here.";
            list.append(item);
            return;
        }

        state.activities.slice(0, 5).forEach((activity) => {
            const item = document.createElement("li");
            const message = document.createElement("strong");
            const time = document.createElement("time");
            message.textContent = activity.message;
            time.textContent = timeAgo(activity.time);
            item.append(message, time);
            list.append(item);
        });
    };

    const renderBattleStats = () => {
        const list = document.getElementById("battleStatList");
        const values = trainingOptions.map((option) => ({
            ...option,
            value: state[option.stat],
        }));
        const maximum = Math.max(25, ...values.map((item) => item.value));

        list.innerHTML = values.map((item) => `
            <div class="battle-stat">
                <span>${item.title}</span>
                <div class="meter meter--thin"><span class="meter__fill" style="width:${(item.value / maximum) * 100}%"></span></div>
                <strong>${item.value}</strong>
            </div>
        `).join("");

        document.getElementById("battleTotal").textContent = `${values.reduce((sum, item) => sum + item.value, 0)} total`;
        const weapon = state.inventory.find((item) => item.id === state.equipped.weapon)?.name || "Bare hands";
        const armour = state.inventory.find((item) => item.id === state.equipped.armour)?.name || "Street clothes";
        document.getElementById("equippedWeapon").textContent = weapon;
        document.getElementById("equippedArmour").textContent = armour;
    };

    const availableTrainingSets = () => Math.floor(state.energy / GYM_ENERGY_PER_TRAIN);

    const trainingGainForSets = (sets) => sets * GYM_GAIN_PER_TRAIN;

    const selectedTrainingSets = (statName) => {
        const maximum = availableTrainingSets();

        if (maximum < 1) {
            return 0;
        }

        const requested = number(trainingSets[statName], DEFAULT_TRAINING_SETS);
        return clamp(
            Math.round(requested),
            1,
            maximum,
        );
    };

    const renderTraining = () => {
        const grid = document.getElementById("trainingGrid");
        const maximumSets = availableTrainingSets();
        const restricted = Boolean(state.restriction && state.restriction.until > Date.now());

        grid.innerHTML = trainingOptions.map((option) => {
            const selectedSets = selectedTrainingSets(option.stat);
            const energyCost = selectedSets * GYM_ENERGY_PER_TRAIN;
            const gain = trainingGainForSets(selectedSets);
            const disabled = restricted || selectedSets === 0;
            trainingSets[option.stat] = selectedSets || DEFAULT_TRAINING_SETS;

            return `
                <article class="training-card" style="--stat-colour:${option.colour}">
                    <div class="training-card__head"><span>Current stat</span><strong>${state[option.stat]}</strong></div>
                    <h2>${option.title}</h2>
                    <p>${option.description}</p>
                    <div class="training-investment">
                        <div class="training-investment__summary">
                            <span>Training sets</span>
                            <output data-training-output>${selectedSets} ${selectedSets === 1 ? "train" : "trains"}</output>
                        </div>
                        <input
                            class="training-slider"
                            type="range"
                            min="1"
                            max="${Math.max(1, maximumSets)}"
                            step="1"
                            value="${selectedSets || 1}"
                            data-training-sets="${option.stat}"
                            aria-label="Number of ${option.title} training sets"
                            aria-valuetext="${selectedSets} sets, ${energyCost} energy, estimated gain ${gain}"
                            ${disabled ? "disabled" : ""}
                        >
                        <div class="training-investment__scale">
                            <small>${maximumSets >= 1 ? "1 set" : "0 sets"}</small>
                            <strong data-training-gain>${energyCost} energy · est. +${gain}</strong>
                            <small>${maximumSets} ${maximumSets === 1 ? "set" : "sets"}</small>
                        </div>
                    </div>
                    <button class="train-button" type="button" data-train="${option.stat}" ${disabled ? "disabled" : ""}>
                        ${restricted ? "Currently restricted" : selectedSets === 0 ? `Need ${GYM_ENERGY_PER_TRAIN} energy` : `Train ${selectedSets}× · ${energyCost} energy`}
                    </button>
                </article>
            `;
        }).join("");

        grid.querySelectorAll("[data-training-sets]").forEach((input) => {
            input.addEventListener("input", () => {
                const sets = Number(input.value);
                const energyCost = sets * GYM_ENERGY_PER_TRAIN;
                const statName = input.dataset.trainingSets;
                const gain = trainingGainForSets(sets);
                const card = input.closest(".training-card");

                trainingSets[statName] = sets;
                input.setAttribute("aria-valuetext", `${sets} sets, ${energyCost} energy, estimated gain ${gain}`);
                card.querySelector("[data-training-output]").textContent = `${sets} ${sets === 1 ? "train" : "trains"}`;
                card.querySelector("[data-training-gain]").textContent = `${energyCost} energy · est. +${gain}`;
                card.querySelector("[data-train]").textContent = `Train ${sets}× · ${energyCost} energy`;
            });
        });

        grid.querySelectorAll("[data-train]").forEach((button) => {
            button.addEventListener("click", () => train(button.dataset.train));
        });

        const result = document.getElementById("trainingResult");
        result.hidden = !lastTrainingResult;

        if (lastTrainingResult) {
            result.innerHTML = `
                <span>Session complete</span>
                <strong>You completed ${lastTrainingResult.sets} ${lastTrainingResult.stat.toLowerCase()} ${lastTrainingResult.sets === 1 ? "train" : "trains"}.</strong>
                <p>${lastTrainingResult.energy} energy used · ${lastTrainingResult.stat} +${lastTrainingResult.gain}</p>
            `;
        }
    };

    const train = (statName) => {
        const option = trainingOptions.find((item) => item.stat === statName);
        const sets = selectedTrainingSets(statName);
        const energyCost = sets * GYM_ENERGY_PER_TRAIN;
        const gain = trainingGainForSets(sets);

        if (!option || !canPerformAction()) return;
        if (sets < 1 || state.energy < energyCost) {
            toast("Not enough energy to train.", true);
            return;
        }

        state.energy -= energyCost;
        state[statName] += gain;
        lastTrainingResult = {
            stat: option.title,
            sets,
            energy: energyCost,
            gain,
        };
        advanceDailyObjective("training");
        addActivity(`${option.title} increased by ${gain} across ${sets} training sets`);
        toast(`${option.title} +${gain} · ${energyCost} energy used`);
        saveState();
        renderAll();
    };

    const riskForCrime = (crime) => {
        if (crime.chance >= 70) return ["Low", "low"];
        if (crime.chance >= 50) return ["Medium", "medium"];
        return ["High", "high"];
    };

    const renderCrimeFilters = () => {
        const filters = ["All", "Camden", "Brixton", "Soho"];
        const row = document.getElementById("crimeFilters");
        row.innerHTML = filters.map((filter) => `
            <button class="filter-button${activeCrimeFilter === filter ? " is-active" : ""}" type="button" data-crime-filter="${filter}">${filter}</button>
        `).join("");
        row.querySelectorAll("[data-crime-filter]").forEach((button) => {
            button.addEventListener("click", () => {
                activeCrimeFilter = button.dataset.crimeFilter;
                renderCrimes();
            });
        });
    };

    const renderCrimes = () => {
        renderCrimeFilters();
        const grid = document.getElementById("crimeGrid");
        const visible = crimes.filter((crime) => activeCrimeFilter === "All" || crime.district === activeCrimeFilter);
        const restricted = Boolean(state.restriction && state.restriction.until > Date.now());

        grid.innerHTML = visible.map((crime) => {
            const [risk, riskClass] = riskForCrime(crime);
            const unavailable = restricted || state.nerve < crime.nerve;
            return `
                <article class="crime-card">
                    <div class="crime-card__top"><span class="district-tag">${crime.district}</span><span class="risk-tag risk-tag--${riskClass}">${risk} risk</span></div>
                    <h2>${crime.name}</h2>
                    <p>${crime.description}</p>
                    <div class="crime-stats">
                        <div><small>Success</small><strong>${crime.chance}%</strong></div>
                        <div><small>Reward</small><strong>£${crime.reward[0]}–£${crime.reward[1]}</strong></div>
                        <div><small>Nerve</small><strong>${crime.nerve}</strong></div>
                        <div><small>Wanted</small><strong>+${crime.wanted}</strong></div>
                    </div>
                    <button class="action-button" type="button" data-crime-id="${crime.id}" ${unavailable ? "disabled" : ""}>${restricted ? "Currently restricted" : state.nerve < crime.nerve ? "Not enough nerve" : "Attempt crime"}</button>
                </article>
            `;
        }).join("");

        grid.querySelectorAll("[data-crime-id]").forEach((button) => {
            button.addEventListener("click", () => attemptCrime(button.dataset.crimeId));
        });
    };

    const applyXp = (amount) => {
        state.xp += amount;
        let levelsGained = 0;

        while (state.xp >= state.nextLevelXp) {
            state.level += 1;
            levelsGained += 1;
            state.nextLevelXp += state.level * 100;
        }

        if (levelsGained > 0) {
            toast(`Level up! You are now level ${state.level}.`);
            addActivity(`Reached level ${state.level}`);
        }
    };

    const claimDailyReward = () => {
        const allComplete = completedDailyObjectives() === dailyObjectives.length;

        if (!allComplete || state.daily.rewardClaimed) {
            return;
        }

        state.daily.rewardClaimed = true;
        state.money += dailyReward.cash;
        applyXp(dailyReward.xp);
        addActivity(`Daily objectives: earned ${formatMoney(dailyReward.cash)} and ${dailyReward.xp} XP`);
        saveState();
        renderAll();
        toast(`Daily reward claimed · ${formatMoney(dailyReward.cash)} + ${dailyReward.xp} XP`);
    };

    const attemptCrime = (crimeId) => {
        const crime = crimes.find((item) => item.id === crimeId);
        if (!crime || !canPerformAction()) return;
        if (state.nerve < crime.nerve) {
            toast("Not enough nerve.", true);
            return;
        }

        state.nerve -= crime.nerve;
        state.wanted = clamp(state.wanted + crime.wanted, 0, 100);
        advanceDailyObjective("crimes");
        const success = randomBetween(1, 100) <= crime.chance;

        if (success) {
            const reward = randomBetween(crime.reward[0], crime.reward[1]);
            state.money += reward;
            applyXp(crime.xp);
            addActivity(`${crime.name}: earned ${formatMoney(reward)}`);
            toast(`Crime successful · ${formatMoney(reward)}`);

            if (Math.random() < .16) {
                const tea = state.inventory.find((item) => item.id === "energy-tea");
                if (tea) tea.quantity += 1;
                addActivity("Found a strong tea");
            }
        } else {
            const consequence = randomBetween(1, 100);

            if (consequence <= crime.hospitalChance) {
                const damage = randomBetween(5, 15);
                state.health = clamp(state.health - damage, 0, 100);
                state.restriction = { kind: "hospital", until: Date.now() + crime.restrictionSeconds * 1000 };
                addActivity(`${crime.name}: sent to hospital`);
                toast(`Crime failed · hospitalised with ${damage} damage`, true);
            } else if (consequence <= crime.hospitalChance + crime.jailChance) {
                state.restriction = { kind: "jail", until: Date.now() + crime.restrictionSeconds * 1000 };
                addActivity(`${crime.name}: arrested`);
                toast("Crime failed · sent to jail", true);
            } else {
                const damage = randomBetween(5, 15);
                state.health = clamp(state.health - damage, 0, 100);
                addActivity(`${crime.name}: failed and lost ${damage} health`);
                toast(`Crime failed · ${damage} damage`, true);
            }

            if (state.health === 0 && !state.restriction) {
                state.restriction = { kind: "hospital", until: Date.now() + 120000 };
            }
        }

        saveState();
        renderAll();
    };

    const renderJobs = () => {
        const grid = document.getElementById("jobGrid");
        const active = jobs.find((job) => job.id === state.activeJob);
        const shift = state.workShift;
        const shiftJob = shift ? jobs.find((job) => job.id === shift.jobId) : null;
        const remaining = shift ? Math.max(0, shift.completesAt - Date.now()) : 0;
        const shiftReady = Boolean(shift && remaining === 0);
        const shiftProgress = shift
            ? clamp(((JOB_SHIFT_DURATION_MS - remaining) / JOB_SHIFT_DURATION_MS) * 100, 0, 100)
            : 0;
        const status = document.getElementById("activeJobStatus");

        if (!active) {
            status.innerHTML = `<small>Current position</small><strong>Unemployed</strong>`;
        } else if (!shift) {
            status.innerHTML = `<small>Current position</small><strong>${active.title}</strong><span class="job-status__timer">Ready for a shift</span>`;
        } else {
            status.innerHTML = `
                <small>${shiftReady ? "Shift finished" : "Shift in progress"}</small>
                <strong>${shiftJob?.title || active.title}</strong>
                <span class="job-status__timer${shiftReady ? " is-ready" : ""}">${shiftReady ? "Pay ready to collect" : `${formatShiftDuration(remaining)} remaining`}</span>
                <div class="job-progress" role="progressbar" aria-label="Job shift progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(shiftProgress)}">
                    <span style="width:${shiftProgress}%"></span>
                </div>
            `;
        }

        grid.innerHTML = jobs.map((job) => {
            const locked = state.level < job.level;
            const current = state.activeJob === job.id;
            const shiftForJob = shift?.jobId === job.id;
            const readyForJob = shiftForJob && shiftReady;
            const blockedByShift = Boolean(shift && !shiftForJob);
            const insufficientEnergy = current && !shift && state.energy < job.energy;
            const working = shiftForJob && !shiftReady;
            let label = "Apply for job";

            if (locked) label = `Unlocks at level ${job.level}`;
            else if (readyForJob) label = `Collect ${formatMoney(job.pay)} + ${job.xp} XP`;
            else if (working) label = `Working · ${formatShiftDuration(remaining)}`;
            else if (blockedByShift) label = "Another shift is active";
            else if (current && insufficientEnergy) label = `Need ${job.energy} energy`;
            else if (current) label = `Start 3h shift · ${job.energy} energy`;

            const disabled = locked || working || blockedByShift || insufficientEnergy;
            const employmentLabel = readyForJob
                ? "Pay ready"
                : working
                    ? "Working"
                    : current
                        ? "Employed"
                        : `Level ${job.level}`;
            const employmentClass = working
                ? "risk-tag--medium"
                : readyForJob || current
                    ? "risk-tag--low"
                    : "";

            return `
                <article class="job-card${current ? " is-active" : ""}${working ? " is-working" : ""}${readyForJob ? " is-ready" : ""}">
                    <div class="job-card__top"><span class="district-tag">${job.company}</span><span class="risk-tag ${employmentClass}">${employmentLabel}</span></div>
                    <h2>${job.title}</h2>
                    <p>${job.description}</p>
                    <span class="job-card__duration">Shifts run for 3 real hours</span>
                    <div class="job-stats job-stats--three">
                        <div><small>Shift pay</small><strong>${formatMoney(job.pay)}</strong></div>
                        <div><small>Job XP</small><strong>+${job.xp}</strong></div>
                        <div><small>Duration</small><strong>3 hours</strong></div>
                    </div>
                    <button class="action-button" type="button" data-job-id="${job.id}" ${disabled ? "disabled" : ""}>${label}</button>
                </article>
            `;
        }).join("");

        grid.querySelectorAll("[data-job-id]").forEach((button) => {
            button.addEventListener("click", () => handleJob(button.dataset.jobId));
        });
    };

    const handleJob = (jobId) => {
        const job = jobs.find((item) => item.id === jobId);

        if (!job || state.level < job.level || !canPerformAction()) return;

        if (state.workShift) {
            if (state.workShift.jobId !== job.id) {
                toast("Finish your current shift before changing jobs.", true);
                return;
            }

            const remaining = state.workShift.completesAt - Date.now();

            if (remaining > 0) {
                toast(`Shift still in progress · ${formatShiftDuration(remaining)} remaining`, true);
                return;
            }

            state.workShift = null;
            state.money += job.pay;
            applyXp(job.xp);
            advanceDailyObjective("shifts");
            addActivity(`${job.title} shift collected: ${formatMoney(job.pay)}`);
            toast(`Shift collected · ${formatMoney(job.pay)} · ${job.xp} XP`);
            saveState();
            renderAll();
            return;
        }

        if (state.activeJob !== job.id) {
            state.activeJob = job.id;
            addActivity(`Started work as ${job.title}`);
            toast(`Hired by ${job.company}`);
        } else {
            if (state.energy < job.energy) {
                toast("Not enough energy to start this shift.", true);
                return;
            }

            const startedAt = Date.now();
            state.energy -= job.energy;
            state.workShift = {
                jobId: job.id,
                startedAt,
                completesAt: startedAt + JOB_SHIFT_DURATION_MS,
            };
            addActivity(`Started a three-hour ${job.title} shift`);
            toast("Shift started · ready in 3 hours");
        }

        saveState();
        renderAll();
    };
    const renderInventoryFilters = () => {
        const filters = [
            { key: "All", label: "All items", icon: "bag" },
            { key: "medical", label: "Medical", icon: "medical" },
            { key: "boost", label: "Boosts", icon: "bolt" },
            { key: "weapon", label: "Weapons", icon: "weapon" },
            { key: "armour", label: "Armour", icon: "shield" },
            { key: "utility", label: "Utility", icon: "utility" },
        ];
        const row = document.getElementById("inventoryFilters");
        row.innerHTML = filters.map((filter) => `
            <button class="filter-button filter-button--icon${activeInventoryFilter === filter.key ? " is-active" : ""}" type="button" data-item-filter="${filter.key}">
                <svg aria-hidden="true"><use href="#icon-${filter.icon}"></use></svg>
                <span>${filter.label}</span>
            </button>
        `).join("");
        row.querySelectorAll("[data-item-filter]").forEach((button) => {
            button.addEventListener("click", () => {
                activeInventoryFilter = button.dataset.itemFilter;
                renderInventory();
            });
        });
    };

    const renderInventory = () => {
        renderInventoryFilters();
        const items = state.inventory.filter((item) => item.quantity > 0 && (activeInventoryFilter === "All" || item.type === activeInventoryFilter));
        const grid = document.getElementById("inventoryGrid");
        grid.innerHTML = items.map((item) => {
            const equipped = state.equipped.weapon === item.id || state.equipped.armour === item.id;
            return `
                <article class="inventory-card">
                    <div class="inventory-card__icon">${item.icon}</div>
                    <span class="inventory-card__type">${item.type}</span>
                    <h3>${item.name}</h3>
                    <p>${item.description}</p>
                    <footer><span>Quantity ${item.quantity}</span><button class="item-button" type="button" data-item-id="${item.id}" ${item.action === "Keep" ? "disabled" : ""}>${equipped ? "Equipped" : item.action}</button></footer>
                </article>
            `;
        }).join("") || `<article class="panel"><p>No items in this category.</p></article>`;

        grid.querySelectorAll("[data-item-id]").forEach((button) => {
            button.addEventListener("click", () => useItem(button.dataset.itemId));
        });

        const count = state.inventory.reduce((sum, item) => sum + item.quantity, 0);
        document.getElementById("inventoryCount").textContent = count;
        document.getElementById("inventoryCapacity").textContent = count;

        const weapon = state.inventory.find((item) => item.id === state.equipped.weapon)?.name || "Bare hands";
        const armour = state.inventory.find((item) => item.id === state.equipped.armour)?.name || "Street clothes";
        document.getElementById("loadoutWeapon").textContent = weapon;
        document.getElementById("loadoutArmour").textContent = armour;
    };

    const useItem = (itemId) => {
        const item = state.inventory.find((entry) => entry.id === itemId);
        if (!item || item.quantity <= 0) return;

        if (item.type === "medical") {
            if (state.health >= 100) {
                toast("Your health is already full.");
                return;
            }
            state.health = clamp(state.health + 25, 0, 100);
            item.quantity -= 1;
            toast("Health restored by 25.");
        } else if (item.type === "boost") {
            if (state.energy >= state.maxEnergy) {
                toast("Your energy is already full.");
                return;
            }
            state.energy = clamp(state.energy + 20, 0, state.maxEnergy);
            item.quantity -= 1;
            toast("Energy restored by 20.");
        } else if (item.type === "weapon") {
            state.equipped.weapon = item.id;
            toast(`${item.name} equipped.`);
        } else if (item.type === "armour") {
            state.equipped.armour = item.id;
            toast(`${item.name} equipped.`);
        }

        addActivity(`${item.name}: ${item.type === "weapon" || item.type === "armour" ? "equipped" : "used"}`);
        saveState();
        renderAll();
    };

    const renderDistrict = () => {
        const details = districts[selectedDistrict];
        const panel = document.getElementById("districtDetails");
        panel.innerHTML = `
            <span class="district-details__tag">Selected district</span>
            <h2>${selectedDistrict}</h2>
            <p>${details.description}</p>
            <dl><div><dt>Risk level</dt><dd>${details.risk}</dd></div><div><dt>Known for</dt><dd>${details.speciality}</dd></div><div><dt>Venue</dt><dd>${details.venue}</dd></div></dl>
            <button class="action-button" id="travelButton" type="button" ${state.district === selectedDistrict ? "disabled" : ""}>${state.district === selectedDistrict ? "Current location" : "Travel here · 2 energy"}</button>
        `;
        document.querySelectorAll("[data-district]").forEach((button) => {
            button.classList.toggle("is-current", button.dataset.district === state.district);
        });
        document.getElementById("travelButton").addEventListener("click", travelToDistrict);
    };

    const travelToDistrict = () => {
        if (state.district === selectedDistrict) return;
        if (!canPerformAction()) return;
        if (state.energy < 2) {
            toast("Not enough energy to travel.", true);
            return;
        }
        state.energy -= 2;
        state.district = selectedDistrict;
        addActivity(`Travelled to ${selectedDistrict}`);
        toast(`Arrived in ${selectedDistrict}`);
        saveState();
        renderAll();
    };

    const slotSymbols = ["7", "£", "♛", "◆", "☕", "★"];

    const shuffled = (values) => {
        const result = [...values];

        for (let index = result.length - 1; index > 0; index -= 1) {
            const swapIndex = randomBetween(0, index);
            [result[index], result[swapIndex]] = [result[swapIndex], result[index]];
        }

        return result;
    };

    const generateSlotResult = () => {
        const roll = Math.random() * 100;

        if (roll < .2) return ["7", "7", "7"];
        if (roll < 1) return ["£", "£", "£"];

        if (roll < 3) {
            const symbol = ["♛", "◆", "☕", "★"][randomBetween(0, 3)];
            return [symbol, symbol, symbol];
        }

        if (roll < 18) {
            const pair = slotSymbols[randomBetween(0, slotSymbols.length - 1)];
            const remaining = slotSymbols.filter((symbol) => symbol !== pair);
            const other = remaining[randomBetween(0, remaining.length - 1)];
            return shuffled([pair, pair, other]);
        }

        return shuffled(slotSymbols).slice(0, 3);
    };

    const renderBets = () => {
        const selector = document.getElementById("betSelector");
        selector.innerHTML = [10, 50, 100, 500].map((bet) => `
            <button class="bet-button${state.selectedBet === bet ? " is-active" : ""}" type="button" data-bet="${bet}">£${bet}</button>
        `).join("");
        selector.querySelectorAll("[data-bet]").forEach((button) => {
            button.addEventListener("click", () => {
                state.selectedBet = Number(button.dataset.bet);
                saveState();
                renderBets();
            });
        });
        document.getElementById("spinButton").disabled = spinning || state.money < state.selectedBet;
    };

    const spinSlots = () => {
        if (spinning || !canPerformAction()) return;
        const bet = state.selectedBet;
        if (state.money < bet) {
            toast("Not enough cash for that stake.", true);
            return;
        }

        spinning = true;
        state.money -= bet;
        updateCoreUI();
        renderBets();
        const reels = [...document.querySelectorAll(".slot-reel")];
        reels.forEach((reel) => reel.classList.add("is-spinning"));
        document.getElementById("slotResult").textContent = "Reels spinning…";

        window.setTimeout(() => {
            const result = generateSlotResult();
            reels.forEach((reel, index) => {
                reel.textContent = result[index];
                reel.classList.remove("is-spinning");
            });

            let multiplier = 0;
            if (result.every((symbol) => symbol === "7")) multiplier = 10;
            else if (result.every((symbol) => symbol === "£")) multiplier = 6;
            else if (new Set(result).size === 1) multiplier = 4;
            else if (new Set(result).size === 2) multiplier = 2;

            const winnings = bet * multiplier;
            if (winnings > 0) {
                state.money += winnings;
                document.getElementById("slotResult").textContent = `Winner · ${formatMoney(winnings)}`;
                addActivity(`Casino win: ${formatMoney(winnings)}`);
                toast(`Slots paid ${formatMoney(winnings)}`);
            } else {
                document.getElementById("slotResult").textContent = `No win · ${formatMoney(bet)} lost`;
                addActivity(`Casino: lost ${formatMoney(bet)}`);
            }

            spinning = false;
            saveState();
            renderAll();
        }, 850);
    };

    const renderAll = () => {
        updateCoreUI();
        updateRestriction();
        renderDailyObjectives();
        renderActivity();
        renderBattleStats();
        renderTraining();
        renderCrimes();
        renderJobs();
        renderInventory();
        renderDistrict();
        renderBets();
    };

    const showView = (viewName, { updateHash = true, moveFocus = true } = {}) => {
        const targetView = [...document.querySelectorAll("[data-view]")].find(
            (view) => view.dataset.view === viewName,
        );

        if (!targetView) {
            return;
        }

        document.querySelectorAll("[data-view]").forEach((view) => {
            const active = view.dataset.view === viewName;
            view.hidden = !active;
            view.classList.toggle("is-active", active);
        });

        document.querySelectorAll("[data-view-target]").forEach((button) => {
            const active = button.dataset.viewTarget === viewName;
            button.classList.toggle("is-active", active);

            if (active && button.closest("nav")) {
                button.setAttribute("aria-current", "page");
            } else {
                button.removeAttribute("aria-current");
            }
        });

        const sidebar = document.getElementById("gameSidebar");
        const scrim = document.getElementById("sidebarScrim");
        sidebar.classList.remove("is-open");
        scrim.classList.remove("is-visible");
        document.getElementById("mobileMenuButton").setAttribute("aria-expanded", "false");
        document.getElementById("mainContent").scrollIntoView({ behavior: "smooth", block: "start" });

        if (updateHash && window.location.hash !== `#${viewName}`) {
            window.history.pushState({ view: viewName }, "", `#${viewName}`);
        }

        if (moveFocus) {
            const heading = targetView.querySelector("h1");
            if (heading) {
                heading.setAttribute("tabindex", "-1");
                window.requestAnimationFrame(() => heading.focus({ preventScroll: true }));
            }
        }
    };

    document.querySelectorAll("[data-view-target]").forEach((button) => {
        button.addEventListener("click", () => showView(button.dataset.viewTarget));
    });

    const sidebar = document.getElementById("gameSidebar");
    const scrim = document.getElementById("sidebarScrim");
    const menuButton = document.getElementById("mobileMenuButton");
    menuButton.addEventListener("click", () => {
        const open = sidebar.classList.toggle("is-open");
        scrim.classList.toggle("is-visible", open);
        menuButton.setAttribute("aria-expanded", String(open));
    });
    scrim.addEventListener("click", () => {
        sidebar.classList.remove("is-open");
        scrim.classList.remove("is-visible");
        menuButton.setAttribute("aria-expanded", "false");
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !sidebar.classList.contains("is-open")) return;
        sidebar.classList.remove("is-open");
        scrim.classList.remove("is-visible");
        menuButton.setAttribute("aria-expanded", "false");
        menuButton.focus();
    });

    document.querySelectorAll("[data-district]").forEach((button) => {
        button.addEventListener("click", () => {
            selectedDistrict = button.dataset.district;
            renderDistrict();
        });
    });

    document.getElementById("claimDailyReward").addEventListener("click", claimDailyReward);
    document.getElementById("spinButton").addEventListener("click", spinSlots);
    document.getElementById("resetPrototype").addEventListener("click", () => {
        if (!window.confirm("Reset all browser-only prototype progress?")) return;
        localStorage.removeItem(storageKey);
        state = createInitialState();
        activeCrimeFilter = "All";
        activeInventoryFilter = "All";
        selectedDistrict = state.district;
        lastTrainingResult = null;
        saveState();
        renderAll();
        toast("Frontend prototype reset.");
    });

    window.setInterval(updateRestriction, 1000);
    window.setInterval(() => {
        if (state.workShift) renderJobs();
    }, 1000);
    window.setInterval(renderActivity, 30000);
    renderAll();

    const initialView = window.location.hash.slice(1);
    showView(
        [...document.querySelectorAll("[data-view]")].some((view) => view.dataset.view === initialView)
            ? initialView
            : "overview",
        { updateHash: false, moveFocus: false },
    );

    window.addEventListener("popstate", () => {
        const requestedView = window.location.hash.slice(1) || "overview";
        showView(requestedView, { updateHash: false, moveFocus: false });
    });
})();
