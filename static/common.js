// Petits outils partagés par les trois pages.
// Règle de sécurité : on construit le DOM avec textContent / createTextNode, jamais avec du HTML brut,
// car les prénoms et les réponses du gardien sont du texte non fiable.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === false || value == null) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export async function api(path, { method = "GET", body, headers = {} } = {}) {
  let resp;
  try {
    resp = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json", ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Le serveur ne répond pas. Vérifie qu'il est lancé.");
  }
  let data = null;
  try {
    data = await resp.json();
  } catch {
    /* corps vide ou non JSON */
  }
  if (!resp.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : "Requête refusée.";
    throw new ApiError(resp.status, detail);
  }
  return data;
}

export function formatTime(seconds) {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// localStorage peut être indisponible (navigation privée, politique du navigateur) : on ne plante jamais.
export const memory = {
  get(key) {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      /* ignoré */
    }
  },
  remove(key) {
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* ignoré */
    }
  },
};

// Remplit un emplacement avec le QR d'inscription. Pour l'activer : copier l'image dans static/qr.png.
export function fillQrSlot(slot) {
  const img = h("img", { src: "/static/qr.png", alt: "QR code d'inscription au club" });
  img.addEventListener("load", () => slot.classList.add("has-img"));
  img.addEventListener("error", () => {
    img.remove();
    slot.classList.remove("has-img");
    slot.textContent = "QR code d'inscription";
  });
  slot.replaceChildren(img);
}
