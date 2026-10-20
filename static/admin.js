import { ApiError, api, h, memory } from "/static/common.js";

const TOKEN_KEY = "ctb-admin-token";
const $ = (id) => document.getElementById(id);
const tokenInput = $("token");
const rows = $("rows");
const msg = $("msg");

tokenInput.value = memory.get(TOKEN_KEY) ?? "";

const say = (text, kind = "") => {
  msg.textContent = text;
  msg.className = `msg ${kind}`.trim();
};
const authHeaders = () => ({ "X-Admin-Token": tokenInput.value.trim() });

async function showHealth() {
  const box = $("health");
  try {
    const hl = await api("/api/health");
    box.textContent = `${hl.ok ? "Gardien prêt" : "Gardien indisponible"} : ${hl.detail} (modèle ${hl.model}, backend ${hl.backend}).`;
    box.classList.toggle("warn", !hl.ok);
  } catch (err) {
    box.textContent = err.message;
    box.classList.add("warn");
  }
}

async function load() {
  if (!tokenInput.value.trim()) {
    say("Entre le jeton admin affiché dans le terminal.", "bad");
    return;
  }
  try {
    const data = await api("/api/admin/entries", { headers: authHeaders() });
    memory.set(TOKEN_KEY, tokenInput.value.trim());
    say(data.entries.length ? "" : "Le classement est vide.");
    rows.replaceChildren(
      ...data.entries.map((e) =>
        h(
          "tr",
          {},
          h("td", {}, String(e.rank)),
          h("td", {}, e.name),
          h("td", {}, String(e.levels)),
          h("td", {}, String(e.points)),
          h("td", {}, new Date(e.at * 1000).toLocaleTimeString("fr-FR")),
          h("td", {}, h("button", { class: "btn btn-danger", type: "button", onclick: () => remove(e) }, "Supprimer")),
        ),
      ),
    );
  } catch (err) {
    rows.replaceChildren();
    say(err instanceof ApiError && err.status === 401 ? "Jeton invalide." : err.message, "bad");
  }
}

async function remove(entry) {
  if (!window.confirm(`Supprimer « ${entry.name} » du classement ?`)) return;
  try {
    await api(`/api/admin/entries/${entry.id}`, { method: "DELETE", headers: authHeaders() });
    say(`« ${entry.name} » supprimé.`, "good");
  } catch (err) {
    say(err.message, "bad");
  }
  await load();
}

async function reset() {
  if (!window.confirm("Vider tout le classement ? Une copie de sécurité est conservée dans le dossier data.")) return;
  try {
    const out = await api("/api/admin/reset", { method: "POST", headers: authHeaders(), body: { confirm: true } });
    say(`${out.removed} entrée(s) retirée(s).`, "good");
  } catch (err) {
    say(err.message, "bad");
  }
  await load();
}

$("token-form").addEventListener("submit", (e) => {
  e.preventDefault();
  load();
});
$("reload-btn").addEventListener("click", load);
$("reset-btn").addEventListener("click", reset);

showHealth();
if (tokenInput.value) load();
setInterval(() => {
  showHealth();
  if (tokenInput.value && document.visibilityState === "visible") load();
}, 5000);
