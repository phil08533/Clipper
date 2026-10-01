"use strict";

const STORE = "startpage.v1";
const grid = document.getElementById("grid");

const uid = () => Math.random().toString(36).slice(2, 9);
const DEFAULT_STATE = () => ({
  theme: "auto",
  widgets: ["clock", "weather", "hn", "wiki", "todo", "links"].map((type) => ({ id: uid(), type, wide: false, config: Widgets[type].defaults() }))
});

function load() {
  try {
    const s = JSON.parse(localStorage.getItem(STORE));
    if (s && Array.isArray(s.widgets)) return sanitize(s);
  } catch {}
  return DEFAULT_STATE();
}

// Accepts untrusted JSON (imports) — keep only known widget types and fill missing config.
function sanitize(s) {
  return {
    theme: ["auto", "dark", "light"].includes(s.theme) ? s.theme : "auto",
    widgets: s.widgets.filter((w) => w && Widgets[w.type]).map((w) => ({
      id: typeof w.id === "string" ? w.id : uid(),
      type: w.type,
      wide: !!w.wide || (w.wide === undefined && !!Widgets[w.type].wide),
      config: Object.assign(Widgets[w.type].defaults(), w.config && typeof w.config === "object" ? w.config : {})
    }))
  };
}

let state = load();
let editing = false;
const cleanups = new Map();

function save() {
  try { localStorage.setItem(STORE, JSON.stringify(state)); } catch {}
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  const dark = state.theme === "dark" || (state.theme === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.querySelector('meta[name="theme-color"]').content = dark ? "#0f1115" : "#f4f5f7";
}

/* ---------- rendering ---------- */

function mountWidget(w, body) {
  const prev = cleanups.get(w.id);
  if (prev) prev();
  cleanups.delete(w.id);
  const ctx = { config: w.config, save, refresh: () => mountWidget(w, body) };
  try {
    const cleanup = Widgets[w.type].render(body, ctx);
    if (typeof cleanup === "function") cleanups.set(w.id, cleanup);
  } catch (e) {
    body.replaceChildren(h("p", { class: "err" }, "Widget error: " + e.message));
  }
}

function move(i, delta) {
  const j = i + delta;
  if (j < 0 || j >= state.widgets.length) return;
  state.widgets.splice(j, 0, state.widgets.splice(i, 1)[0]);
  save(); render();
}

function render() {
  cleanups.forEach((fn) => fn());
  cleanups.clear();
  grid.classList.toggle("editing", editing);

  if (!state.widgets.length) {
    grid.replaceChildren(h("p", { class: "muted" }, "Nothing here yet. Tap “+ Add widget” to get started."));
    return;
  }

  grid.replaceChildren(...state.widgets.map((w, i) => {
    const def = Widgets[w.type];
    const body = h("div", { class: "card-body" });
    const card = h("section", { class: "card" + (w.wide ? " wide" : ""), draggable: editing ? "true" : null, "data-id": w.id },
      h("div", { class: "card-head" },
        h("span", {}, def.name),
        h("span", { class: "card-tools" },
          h("button", { class: "btn small", type: "button", "aria-label": "Move earlier", onclick: () => move(i, -1) }, "←"),
          h("button", { class: "btn small", type: "button", "aria-label": "Move later", onclick: () => move(i, 1) }, "→"),
          h("button", { class: "btn small", type: "button", "aria-label": "Toggle width", onclick: () => { w.wide = !w.wide; save(); render(); } }, w.wide ? "▭" : "▬"),
          h("button", { class: "btn small", type: "button", "aria-label": "Remove widget", onclick: () => { state.widgets.splice(i, 1); save(); render(); } }, "✕"))),
      body);
    mountWidget(w, body);
    return card;
  }));
}

/* ---------- drag to reorder (desktop; touch uses the arrow buttons) ---------- */

let dragId = null;
grid.addEventListener("dragstart", (e) => {
  const card = e.target.closest(".card");
  if (!card || !editing) return;
  dragId = card.dataset.id;
  card.classList.add("dragging");
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", dragId);
});
grid.addEventListener("dragover", (e) => {
  if (!dragId) return;
  e.preventDefault();
  grid.querySelectorAll(".drop-target").forEach((c) => c.classList.remove("drop-target"));
  const over = e.target.closest(".card");
  if (over && over.dataset.id !== dragId) over.classList.add("drop-target");
});
grid.addEventListener("drop", (e) => {
  if (!dragId) return;
  e.preventDefault();
  const over = e.target.closest(".card");
  if (over && over.dataset.id !== dragId) {
    const from = state.widgets.findIndex((w) => w.id === dragId);
    const [item] = state.widgets.splice(from, 1);
    const to = state.widgets.findIndex((w) => w.id === over.dataset.id);
    state.widgets.splice(to, 0, item);
    save();
  }
  dragId = null;
  render();
});
grid.addEventListener("dragend", () => { dragId = null; render(); });

/* ---------- top bar & dialogs ---------- */

const $ = (id) => document.getElementById(id);

function greeting() {
  const hr = new Date().getHours();
  $("greeting").textContent = hr < 5 ? "Good night" : hr < 12 ? "Good morning" : hr < 18 ? "Good afternoon" : "Good evening";
}

$("btn-edit").addEventListener("click", (e) => {
  editing = !editing;
  e.currentTarget.setAttribute("aria-pressed", String(editing));
  e.currentTarget.textContent = editing ? "Done" : "Edit layout";
  render();
});

const catalog = $("widget-catalog");
$("btn-add").addEventListener("click", () => {
  catalog.replaceChildren(...Object.entries(Widgets).map(([type, def]) =>
    h("button", { class: "btn", type: "button", onclick: () => {
      state.widgets.push({ id: uid(), type, wide: !!def.wide, config: def.defaults() });
      save(); render(); $("dlg-add").close();
    } }, h("div", { class: "name" }, def.name), h("div", { class: "muted" }, def.desc))));
  $("dlg-add").showModal();
});

$("btn-settings").addEventListener("click", () => {
  $("set-theme").value = state.theme;
  $("set-json").value = JSON.stringify(state, null, 1);
  $("set-msg").textContent = "";
  $("dlg-settings").showModal();
});
$("set-theme").addEventListener("change", (e) => { state.theme = e.target.value; save(); applyTheme(); });
$("btn-export").addEventListener("click", async () => {
  const box = $("set-json");
  box.value = JSON.stringify(state);
  try { await navigator.clipboard.writeText(box.value); $("set-msg").textContent = "Copied."; }
  catch { box.select(); $("set-msg").textContent = "Select and copy the text above."; }
});
$("btn-import").addEventListener("click", () => {
  try {
    const next = sanitize(JSON.parse($("set-json").value));
    state = next; save(); applyTheme(); render();
    $("set-msg").textContent = `Loaded ${next.widgets.length} widgets.`;
  } catch { $("set-msg").textContent = "That doesn't look like a valid layout."; }
});
$("btn-reset").addEventListener("click", () => {
  if (!confirm("Reset to the default layout? Notes, tasks and bookmarks will be lost.")) return;
  state = DEFAULT_STATE(); save(); applyTheme(); render(); $("dlg-settings").close();
});

matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);

/* ---------- boot ---------- */

greeting();
applyTheme();
render();

if ("serviceWorker" in navigator) {
  addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
