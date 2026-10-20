import { api, fillQrSlot, h } from "/static/common.js";

const rows = document.getElementById("rows");
const empty = document.getElementById("empty");
const conn = document.getElementById("conn");
let TOTAL_LEVELS = 2; // remplacé par la valeur du serveur dès qu'on l'a reçue
let configLoaded = false;
const REFRESH_MS = 3000;

fillQrSlot(document.getElementById("qr-slot"));

function squares(levels) {
  return h(
    "span",
    { class: "sqs", role: "img", "aria-label": `${levels} niveau${levels > 1 ? "x" : ""} sur ${TOTAL_LEVELS}` },
    ...Array.from({ length: TOTAL_LEVELS }, (_, i) => h("span", { class: `sq${i < levels ? " on" : ""}` })),
  );
}

function render(entries) {
  empty.hidden = entries.length > 0;
  rows.replaceChildren(
    ...entries.map((e) =>
      h(
        "tr",
        { class: e.rank <= 3 ? "podium" : "" },
        h("td", { class: "rank" }, String(e.rank)),
        h("td", { class: "who" }, e.name),
        h("td", {}, squares(e.levels)),
        h("td", { class: "pts" }, String(e.points)),
      ),
    ),
  );
}

async function loop() {
  try {
    if (!configLoaded) {
      TOTAL_LEVELS = (await api("/api/config")).total_levels;
      configLoaded = true;
    }
    const data = await api("/api/leaderboard?limit=10");
    render(data.entries);
    conn.textContent = "";
  } catch {
    conn.textContent = "Connexion perdue : dernier classement connu affiché.";
  }
  setTimeout(loop, REFRESH_MS); // on attend la fin de la requête avant la suivante : jamais de chevauchement
}

loop();
