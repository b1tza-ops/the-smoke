"use strict";

function formatDuration(totalSeconds) {
    const safeSeconds = Math.max(0, Number(totalSeconds) || 0);
    const hours = Math.floor(safeSeconds / 3600);
    const minutes = Math.floor((safeSeconds % 3600) / 60);
    const seconds = safeSeconds % 60;

    if (hours > 0) {
        return `${hours}h ${String(minutes).padStart(2, "0")}m ${String(seconds).padStart(2, "0")}s`;
    }

    return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

document.querySelectorAll("[data-countdown]").forEach((element) => {
    let remaining = Number(element.dataset.countdown) || 0;

    const update = () => {
        element.textContent = remaining === 0 ? "Ready — refresh" : formatDuration(remaining);
        remaining = Math.max(0, remaining - 1);
    };

    update();
    window.setInterval(update, 1000);
});
