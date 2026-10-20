import { ApiError, api, fillQrSlot, formatTime, h, memory } from "/static/common.js";

const $ = (id) => document.getElementById(id);
const SESSION_KEY = "ctb-session";

const el = {
  start: $("screen-start"), game: $("screen-game"), end: $("screen-end"),
  rules: $("rules"), startForm: $("start-form"), name: $("name"), startBtn: $("start-btn"), startMsg: $("start-msg"),
  quota: $("quota"), track: $("track"), levelTitle: $("level-title"), timer: $("timer"), timerNote: $("timer-note"),
  log: $("log"), chatForm: $("chat-form"), msg: $("msg"), sendBtn: $("send-btn"),
  guessForm: $("guess-form"), guess: $("guess"), guessBtn: $("guess-btn"), guessMsg: $("guess-msg"),
  quit: $("quit-btn"),
  endTitle: $("end-title"), endPoints: $("end-points"), endDetails: $("end-details"),
  reveal: $("reveal-text"), again: $("again-btn"), qr: $("qr-slot"),
};

let cfg = null;
let state = null; // dernier état renvoyé par le serveur
let remaining = 0; // secondes restantes au moment `syncedAt`
let syncedAt = 0;
let pending = false; // une requête est en cours : le chrono est figé (le serveur le met aussi en pause)
let finishing = false;

const LEVEL_TITLES = () => Object.fromEntries((cfg?.levels ?? []).map((l) => [l.number, l.title]));

function show(name) {
  el.start.hidden = name !== "start";
  el.game.hidden = name !== "game";
  el.end.hidden = name !== "end";
}

/* ---------------------------------------------------------------- chrono */
function currentRemaining() {
  if (!state || state.status !== "running" || pending || state.busy) return remaining;
  return Math.max(0, remaining - (performance.now() - syncedAt) / 1000);
}

function renderTimer() {
  const value = currentRemaining();
  el.timer.textContent = formatTime(value);
  el.timer.classList.toggle("low", state?.status === "running" && value <= 30);
  if (state?.status === "running" && (pending || state.busy)) el.timerNote.textContent = "Chrono en pause pendant que le gardien répond.";
  else if (state?.status === "ready") el.timerNote.textContent = "Le chrono démarre à ton premier message.";
  else el.timerNote.textContent = "";
}

function applyState(next) {
  state = next;
  remaining = next.remaining;
  syncedAt = performance.now();
  if (next.status === "finished") memory.remove(SESSION_KEY);
  else memory.set(SESSION_KEY, next.session_id);
  renderGame();
}

function setPending(value) {
  if (value) {
    remaining = currentRemaining(); // on fige la valeur avant de passer en pause
    syncedAt = performance.now();
  } else {
    syncedAt = performance.now(); // le décompte reprend à partir de maintenant
  }
  pending = value;
  renderGame();
}

async function resync() {
  if (!state) return;
  try {
    applyState(await api(`/api/session/${state.session_id}`));
    if (state.status === "finished") showEnd(state);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      memory.remove(SESSION_KEY);
      state = null;
      show("start");
      setStartMessage("Ta partie a expiré. Tu peux en commencer une nouvelle.", "bad");
    }
  }
}

setInterval(() => {
  if (!state) return;
  renderTimer();
  if (state.status === "running" && !pending && !finishing && currentRemaining() <= 0) {
    finishing = true;
    api(`/api/session/${state.session_id}/finish`, { method: "POST" })
      .then((st) => {
        applyState(st);
        showEnd(st);
      })
      .catch(() => resync())
      .finally(() => {
        finishing = false;
      });
  }
}, 200);

/* ------------------------------------------------------------- affichage */
function renderGame() {
  if (!state || !cfg) return;
  const locked = pending || state.status === "finished";
  const noMessages = state.messages_left <= 0;
  for (const node of [el.guess, el.guessBtn]) node.disabled = locked;
  for (const node of [el.msg, el.sendBtn]) node.disabled = locked || noMessages; // plus de messages : bouton grisé
  el.quota.textContent = noMessages
    ? "Plus de messages. Tu peux encore valider un mot : une erreur terminera la partie."
    : `Messages restants : ${state.messages_left} sur ${state.messages_per_level}`;
  el.quota.classList.toggle("low", noMessages || state.messages_left <= 1);
  el.quit.disabled = state.status === "finished";

  el.track.replaceChildren(
    ...Array.from({ length: state.total_levels }, (_, i) => {
      const number = i + 1;
      const kind = number <= state.levels_passed ? "done" : number === state.level ? "current" : "todo";
      const label = kind === "done" ? "réussi" : kind === "current" ? "en cours" : "à venir";
      return h("li", {}, h("span", { class: `step ${kind}`, "aria-current": kind === "current" ? "step" : false }, String(number), h("span", { class: "sr-only" }, ` niveau ${label}`)));
    }),
  );
  el.levelTitle.textContent = `Niveau ${state.level} : ${LEVEL_TITLES()[state.level] ?? ""}`;
  renderTimer();
}

function addBubble(kind, text, { blocked = false } = {}) {
  const who = kind === "user" ? "Toi : " : "Gardien : ";
  el.log.append(h("div", { class: `bubble ${kind}${blocked ? " blocked" : ""}` }, h("span", { class: "sr-only" }, who), text));
  el.log.scrollTop = el.log.scrollHeight;
}

function addNote(text, kind = "") {
  el.log.append(h("p", { class: `note ${kind}` }, text));
  el.log.scrollTop = el.log.scrollHeight;
}

function addTyping() {
  const node = h("div", { class: "bubble guardian", "aria-label": "Le gardien réfléchit" }, h("span", { class: "dots", "aria-hidden": "true" }, h("span"), h("span"), h("span")));
  el.log.append(node);
  el.log.scrollTop = el.log.scrollHeight;
  return node;
}

function setStartMessage(text, kind = "") {
  el.startMsg.textContent = text;
  el.startMsg.className = `msg ${kind}`.trim();
}

function setGuessMessage(text, kind = "") {
  el.guessMsg.textContent = text;
  el.guessMsg.className = `msg ${kind}`.trim();
}

/* --------------------------------------------------------------- actions */
async function onStart(event) {
  event.preventDefault();
  const name = el.name.value.trim();
  if (!name) {
    setStartMessage("Entre un prénom pour commencer.", "bad");
    return;
  }
  el.startBtn.disabled = true;
  setStartMessage("");
  try {
    const st = await api("/api/session", { method: "POST", body: { name } });
    el.log.replaceChildren();
    setGuessMessage("");
    applyState(st);
    show("game");
    el.msg.focus();
  } catch (err) {
    setStartMessage(err.message, "bad");
  } finally {
    el.startBtn.disabled = false;
  }
}

async function onChat(event) {
  event.preventDefault();
  const text = el.msg.value.trim();
  if (!text || pending || !state) return;
  el.msg.value = "";
  addBubble("user", text);
  setPending(true);
  const typing = addTyping();
  try {
    const out = await api(`/api/session/${state.session_id}/chat`, { method: "POST", body: { message: text } });
    typing.remove();
    addBubble("guardian", out.reply, { blocked: out.blocked });
    setPending(false);
    applyState(out);
    if (out.messages_left <= 0 && out.status !== "finished") {
      addNote("Tu as utilisé tous tes messages. Il te reste à valider un mot : si tu te trompes, la partie se termine.");
    }
  } catch (err) {
    typing.remove();
    addNote(err.message, "error");
    setPending(false);
    await resync();
  }
  if (state?.status !== "finished") el.msg.focus();
  else showEnd(state);
}

async function onGuess(event) {
  event.preventDefault();
  const word = el.guess.value.trim();
  if (!word || pending || !state) return;
  setPending(true);
  try {
    const out = await api(`/api/session/${state.session_id}/guess`, { method: "POST", body: { word } });
    setPending(false);
    el.guess.value = "";
    applyState(out);
    if (out.status === "finished") return showEnd(out);
    if (out.correct) {
      el.log.replaceChildren();
      addNote(`Niveau réussi ! Voici le gardien suivant : ${LEVEL_TITLES()[out.level] ?? ""}.`, "good");
      setGuessMessage("Bien joué.", "good");
      el.msg.focus();
    } else {
      setGuessMessage(`Raté : −${out.penalty} s sur ton chrono.`, "bad");
      el.guess.focus();
    }
  } catch (err) {
    setPending(false);
    setGuessMessage(err.message, "bad");
    await resync();
  }
}

async function onQuit() {
  if (!state || state.status === "finished") return;
  if (!window.confirm("Terminer la partie maintenant ? Ton score actuel sera enregistré.")) return;
  setPending(true);
  try {
    const st = await api(`/api/session/${state.session_id}/finish`, { method: "POST" });
    setPending(false);
    applyState(st);
    showEnd(st);
  } catch (err) {
    setPending(false);
    addNote(err.message, "error");
    await resync();
  }
}

function plural(n, one, many) {
  return `${n} ${n > 1 ? many : one}`;
}

function showEnd(st) {
  const result = st.result ?? { points: 0, levels: 0, time_left: 0, rank: null };
  const title =
    {
      complete: `Tu as craqué les ${st.total_levels} gardiens !`,
      timeout: "Temps écoulé.",
      out_of_messages: "Plus de messages, et le mot était faux.",
      quit: "Partie terminée.",
    }[st.finish_reason] ?? "Partie terminée.";
  el.endTitle.textContent = title;
  el.endPoints.textContent = String(result.points);
  const parts = [`${plural(result.levels, "niveau réussi", "niveaux réussis")} sur ${st.total_levels}.`];
  if (result.levels > 0) parts.push(`Il te restait ${formatTime(result.time_left)} au dernier niveau réussi.`);
  if (result.rank) parts.push(`Place n° ${result.rank} au classement pour le moment.`);
  el.endDetails.textContent = parts.join(" ");
  el.reveal.textContent =
    result.levels > 0
      ? "Tu as écrit des instructions pour faire dire à un modèle d'IA ce qu'il devait cacher, puis tu as contourné ses défenses. Ça s'appelle le prompt engineering, et on l'enseigne dès la Session 2 dans le département IA."
      : "Tu as essayé de faire parler un modèle d'IA qui garde un secret. Ça s'appelle le prompt engineering, et on t'apprend à le maîtriser dès la Session 2 dans le département IA.";
  fillQrSlot(el.qr);
  show("end");
  el.again.focus();
}

function onAgain() {
  state = null;
  el.name.value = "";
  setStartMessage("");
  show("start");
  el.name.focus();
}

/* ------------------------------------------------------------- démarrage */
function renderRules() {
  const limit = formatTime(cfg.time_limit);
  const rules = [
    `Tu as ${limit} au total, et le chrono démarre à ton premier message.`,
    `${cfg.total_levels} gardiens se suivent, de plus en plus méfiants. Chacun protège un mot secret différent.`,
    `Tu as ${cfg.messages_per_level} messages par gardien. Écris-lui pour l'amener à dire son mot, puis tape ce mot dans « Valider ».`,
    `Un mot faux coûte ${cfg.wrong_guess_penalty} secondes. Sans message restant, un mot faux termine la partie.`,
    "Le chrono s'arrête pendant que le gardien répond.",
    "Le score compte les niveaux réussis, puis le temps qu'il te reste. Les 3 meilleurs gagnent un prix.",
  ];
  el.rules.replaceChildren(...rules.map((r) => h("li", {}, r)));
}

async function init() {
  el.startForm.addEventListener("submit", onStart);
  el.chatForm.addEventListener("submit", onChat);
  el.guessForm.addEventListener("submit", onGuess);
  el.quit.addEventListener("click", onQuit);
  el.again.addEventListener("click", onAgain);

  try {
    cfg = await api("/api/config");
  } catch (err) {
    setStartMessage(err.message, "bad");
    el.startBtn.disabled = true;
    return;
  }
  renderRules();

  api("/api/health")
    .then((health) => {
      if (!health.ok) setStartMessage(`Le gardien n'est pas prêt : ${health.detail}`, "bad");
    })
    .catch(() => {});

  // Reprise après un rechargement accidentel de la page (le chrono, lui, a continué côté serveur).
  const saved = memory.get(SESSION_KEY);
  if (saved) {
    try {
      const st = await api(`/api/session/${saved}`);
      if (st.status === "finished") {
        memory.remove(SESSION_KEY);
      } else {
        applyState(st);
        show("game");
        addNote("Partie reprise. Le début de la conversation n'est pas affiché, mais ton chrono et ton niveau sont intacts.");
        return;
      }
    } catch {
      memory.remove(SESSION_KEY);
    }
  }
  show("start");
  el.name.focus();
}

init();
