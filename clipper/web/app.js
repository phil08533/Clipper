"use strict";

/* ============================================================
   Utilities
   ============================================================ */

const PROPS = new Set(["value", "checked", "selected", "disabled", "indeterminate"]);

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (PROPS.has(k)) el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const ICON_PATHS = {
  overview: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  campaigns: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  library: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m10 9 5 3-5 3z"/>',
  prompts: '<path d="M4 5h16v11H8l-4 4z"/><path d="M8 9h8M8 12h5"/>',
  accounts: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>',
  bolt: '<path d="M13 3 4 14h7l-1 7 9-11h-7z"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5M5 20h14"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5M5 20h14"/>',
};

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICON_PATHS[name] || "";
  return svg;
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch {}
  if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status})`);
  return data;
}
const GET = (p) => api("GET", p);

function toast(msg, kind) {
  const t = h("div", { class: "toast" + (kind === "error" ? " error" : "") }, msg);
  document.getElementById("toasts").append(t);
  setTimeout(() => t.remove(), kind === "error" ? 6000 : 3200);
}

async function attempt(fn, okMsg) {
  try {
    const r = await fn();
    if (okMsg) toast(okMsg);
    return r;
  } catch (e) {
    toast(e.message, "error");
    return undefined;
  }
}

/* ---------- time ---------- */

function rel(ts) {
  if (!ts) return "—";
  const d = ts * 1000 - Date.now(), a = Math.abs(d) / 1000;
  const unit = a < 60 ? "just now" : a < 3600 ? `${Math.round(a / 60)} min` : a < 86400 ? `${Math.round(a / 3600)} h` : `${Math.round(a / 86400)} d`;
  if (unit === "just now") return unit;
  return d > 0 ? `in ${unit}` : `${unit} ago`;
}

function when(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000), now = new Date();
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const days = Math.round((new Date(d).setHours(0, 0, 0, 0) - new Date(now).setHours(0, 0, 0, 0)) / 86400000);
  if (days === 0) return `Today, ${time}`;
  if (days === 1) return `Tomorrow, ${time}`;
  if (days === -1) return `Yesterday, ${time}`;
  return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }) + `, ${time}`;
}

const clock = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const hourLabel = (hr) => new Date(2000, 0, 1, hr).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

/* ---------- status ---------- */

const VIDEO_STATUS = {
  queued: ["Queued", ""], generating: ["Generating", "blue"], needs_review: ["Needs review", "amber"],
  ready: ["Ready", "green"], approved: ["Approved", "green"], rejected: ["Rejected", ""],
  failed: ["Failed", "red"], posting: ["Posting", "blue"], posted: ["Posted", "green"],
  partial: ["Partly posted", "amber"], retrying: ["Retrying", "amber"], post_failed: ["Post failed", "red"],
  check: ["Check post", "amber"],
};
const POST_STATUS = {
  pending: ["Pending", ""], posting: ["Posting", "blue"], posted: ["Posted", "green"], failed: ["Failed", "red"],
  unconfirmed: ["Unconfirmed", "amber"], skipped: ["Skipped", ""],
};
const ACCOUNT_STATUS = {
  connected: ["Connected", "green"], not_connected: ["Not connected", ""], checking: ["Checking", "blue"],
  login_open: ["Waiting for sign-in", "blue"], error: ["Error", "red"],
};
const PLATFORM_NAMES = { youtube: "YouTube", tiktok: "TikTok", instagram: "Instagram" };
const PLATFORM_MONO = { youtube: "YT", tiktok: "TT", instagram: "IG" };

function pill(map, status) {
  const [label, color] = map[status] || [status, ""];
  return h("span", { class: "pill " + color }, label);
}

/* ============================================================
   Shell: navigation, autopilot, router, polling
   ============================================================ */

const NAV = [
  ["overview", "Overview"], ["campaigns", "Campaigns"], ["library", "Library"],
  ["prompts", "Prompts"], ["accounts", "Accounts"], ["activity", "Activity"], ["settings", "Settings"],
];

let shellData = { autopilot: false, review: 0, nextPost: null };

function renderNav() {
  const section = (location.hash.split("/")[1] || "overview");
  const nav = document.getElementById("nav");
  nav.replaceChildren(...NAV.map(([key, label]) =>
    h("a", { href: `#/${key}`, class: section === key ? "active" : "" }, icon(key), label,
      key === "library" && shellData.review ? h("span", { class: "badge", title: "Awaiting review" }, shellData.review) : null)));

  const ap = document.getElementById("autopilot");
  const on = shellData.autopilot;
  const sw = h("label", { class: "switch", title: on ? "Pause autopilot" : "Start autopilot" },
    h("input", { type: "checkbox", checked: on, "aria-label": "Autopilot", onchange: async (e) => {
      const want = e.target.checked;
      if (want && !confirm("Start autopilot? Clipper will generate and post on each enabled campaign's schedule.")) { e.target.checked = false; return; }
      await attempt(() => api("POST", "/api/autopilot", { on: want }), want ? "Autopilot started" : "Autopilot paused");
      refreshShell();
    } }), h("span"));
  ap.replaceChildren(
    h("div", { class: "row" }, h("span", { class: "row" }, h("span", { class: "dot" + (on ? " on" : "") }), h("span", { class: "label" }, "Autopilot")), sw),
    h("div", { class: "sub" }, on ? (shellData.nextPost ? `Running · next post ${when(shellData.nextPost)}` : "Running") : "Paused — nothing posts automatically"));
}

async function refreshShell() {
  try {
    const o = await GET("/api/overview");
    const next = o.campaigns.filter((c) => c.enabled && c.next_post_at).map((c) => c.next_post_at).sort()[0];
    shellData = { autopilot: o.autopilot, review: o.stats.review, nextPost: next || null };
  } catch {}
  renderNav();
}

let current = null;
let renderToken = 0;

const ROUTES = [
  [/^#\/overview$/, pageOverview],
  [/^#\/campaigns$/, pageCampaigns],
  [/^#\/campaigns\/new(?:\/(\w+))?$/, pageCampaignNew],
  [/^#\/campaigns\/(\d+)$/, pageCampaignEdit],
  [/^#\/library$/, pageLibrary],
  [/^#\/prompts(?:\/(\d+|new))?$/, pagePrompts],
  [/^#\/accounts$/, pageAccounts],
  [/^#\/activity$/, pageActivity],
  [/^#\/settings$/, pageSettings],
];

async function route() {
  if (!location.hash || location.hash === "#/") { location.hash = "#/overview"; return; }
  const token = ++renderToken;
  const root = document.getElementById("page");
  for (const [re, fn] of ROUTES) {
    const m = location.hash.match(re);
    if (m) {
      renderNav();
      current = null;
      const ctl = await fn(root, ...m.slice(1), token);
      if (token === renderToken) current = ctl || null;
      window.scrollTo(0, 0);
      return;
    }
  }
  location.hash = "#/overview";
}

const isStale = (token) => token !== renderToken;

function pageHead(title, sub, actions, crumb) {
  return h("div", { class: "page-head" },
    h("div", {}, crumb ? h("a", { class: "crumb", href: crumb[0] }, icon("back"), crumb[1]) : null,
      h("h1", {}, title), sub ? h("p", {}, sub) : null),
    actions ? h("div", { class: "actions" }, actions) : null);
}

function card(title, body, extra) {
  return h("section", { class: "card" },
    title ? h("div", { class: "card-head" }, h("h2", {}, title), extra || null) : null, body);
}

function emptyState(title, text, action) {
  return h("div", { class: "empty" }, h("strong", {}, title), h("div", {}, text), action ? h("div", { style: "margin-top:14px" }, action) : null);
}

setInterval(() => {
  if (document.hidden) return;
  refreshShell();
  if (current && current.refresh) current.refresh();
}, 5000);

/* ============================================================
   Overview
   ============================================================ */

async function pageOverview(root, token) {
  const o = await GET("/api/overview");
  if (isStale(token)) return;

  const kpis = h("div", { class: "kpis" });
  const upNext = h("div");
  const recent = h("div");
  const now = h("div");
  const activity = h("div");
  const checks = h("div", {}, h("div", { class: "empty" }, "Running checks…"));

  root.replaceChildren(
    pageHead("Overview", "What Clipper is doing and what happens next.", [h("a", { class: "btn primary", href: "#/campaigns/new" }, icon("plus"), "New campaign")]),
    kpis,
    h("div", { class: "grid-2" },
      h("div", { class: "stack" },
        card("Up next", upNext, h("a", { class: "btn ghost sm", href: "#/campaigns" }, "All campaigns")),
        card("Recent videos", recent, h("a", { class: "btn ghost sm", href: "#/library" }, "Open library"))),
      h("div", { class: "stack" },
        card("Right now", now),
        card("System check", checks, h("button", { class: "btn ghost sm", onclick: loadChecks }, icon("refresh"), "Re-check")),
        card("Activity", activity, h("a", { class: "btn ghost sm", href: "#/activity" }, "View all")))));

  function fill(o) {
    kpis.replaceChildren(
      kpi("Posted today", o.posted_today, `Cap ${o.account_cap} per account per day`),
      kpi("Posted, last 7 days", o.stats.posted_7d, "Across all platforms"),
      kpi("Ready to post", o.stats.ready, "Generated and waiting"),
      kpi("Awaiting your review", o.stats.review, o.stats.review ? h("a", { href: "#/library" }, "Review now") : "Nothing to review"));

    const camps = o.campaigns.filter((c) => c.enabled);
    upNext.replaceChildren(camps.length
      ? h("table", { class: "table" },
          h("thead", {}, h("tr", {}, h("th", {}, "Campaign"), h("th", {}, "Posts to"), h("th", {}, "Next post"))),
          h("tbody", {}, camps.map((c) => h("tr", { class: "clickable", onclick: () => (location.hash = `#/campaigns/${c.id}`) },
            h("td", { class: "title-cell" }, c.name),
            h("td", {}, accountChips(c.accounts)),
            h("td", {}, o.autopilot ? (c.next_post_at ? h("span", {}, when(c.next_post_at), h("span", { class: "muted small" }, "  ·  ", rel(c.next_post_at))) : "Scheduling…") : h("span", { class: "muted" }, "Autopilot paused"))))))
      : emptyState("No active campaigns", o.accounts ? "A campaign defines what to make, where to post it and when." : "Start by adding your accounts, then pick a ready-made workflow.",
          h("a", { class: "btn", href: o.accounts ? "#/campaigns/new" : "#/accounts" }, o.accounts ? "Create a campaign" : "Add accounts")));

    recent.replaceChildren(o.recent.length
      ? h("div", {}, o.recent.map((v) => h("div", { class: "list-item clickable", style: "cursor:pointer", onclick: () => openVideo(v.id) },
          v.thumb_url ? h("img", { src: v.thumb_url, alt: "", style: "width:30px;height:53px;object-fit:cover;border-radius:4px" })
                      : h("div", { style: "width:30px;height:53px;border-radius:4px;background:var(--gray-bg)" }),
          h("div", { class: "grow", style: "min-width:0" },
            h("div", { style: "font-weight:550;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" }, v.title || (v.status === "failed" ? "Generation failed" : "Untitled — in progress")),
            h("div", { class: "muted small" }, rel(v.created_at))),
          pill(VIDEO_STATUS, v.status))))
      : emptyState("No videos yet", "Generated videos will appear here."));

    const w = o.worker;
    now.replaceChildren(h("div", {},
      h("div", { class: "list-item" }, h("span", { class: "grow" }, "Generating"),
        w.generating ? h("a", { href: "#", onclick: (e) => { e.preventDefault(); openVideo(w.generating); } }, `Video #${w.generating}`) : h("span", { class: "muted" }, "Idle")),
      h("div", { class: "list-item" }, h("span", { class: "grow" }, "Posting"),
        w.posting.length ? h("span", {}, [...new Set(w.posting)].map((id, i) => [i ? ", " : "", h("a", { href: "#", onclick: (e) => { e.preventDefault(); openVideo(id); } }, `Video #${id}`)])) : h("span", { class: "muted" }, "Idle")),
      h("div", { class: "list-item" }, h("span", { class: "grow" }, "Scheduler"),
        h("span", { class: "muted" }, w.last_tick ? `Checked ${rel(w.last_tick)}` : "Starting"))));

    activity.replaceChildren(o.activity.length ? h("div", {}, o.activity.map(logLine)) : emptyState("No activity yet", ""));
  }

  async function loadChecks() {
    try {
      const r = await GET("/api/health");
      checks.replaceChildren(h("div", {}, r.checks.map((c) =>
        h("div", { class: "check-row" },
          h("span", { class: c.ok ? "ok" : "bad" }, icon(c.ok ? "check" : "alert")),
          h("div", {}, h("div", { style: "font-weight:550" }, c.name), h("div", { class: "muted small" }, c.detail))))));
    } catch (e) { checks.replaceChildren(h("div", { class: "empty" }, e.message)); }
  }

  fill(o);
  loadChecks();
  return { refresh: async () => { try { fill(await GET("/api/overview")); } catch {} } };
}

function kpi(label, value, sub) {
  return h("div", { class: "kpi" }, h("div", { class: "k" }, label), h("div", { class: "v" }, value), h("div", { class: "s" }, sub));
}

function logLine(l) {
  const parts = String(l.message).split(/(screenshots\/[\w.-]+\.png)/);
  return h("div", { class: "log-line " + l.level },
    h("span", { class: "muted", title: new Date(l.ts * 1000).toLocaleString() }, clock(l.ts)),
    h("span", { class: "src" }, PLATFORM_NAMES[l.source] || l.source),
    h("span", { class: "msg" }, parts.map((p) => /^screenshots\//.test(p) ? h("a", { href: "/" + p, target: "_blank" }, "screenshot") : p),
      l.video_id ? h("span", {}, " ", h("a", { href: "#", class: "muted", onclick: (e) => { e.preventDefault(); openVideo(l.video_id); } }, `#${l.video_id}`)) : null));
}

/* ============================================================
   Campaigns
   ============================================================ */

function accountChips(accounts) {
  if (!accounts.length) return h("span", { class: "muted" }, "No accounts");
  return h("span", { class: "acct-list" }, accounts.map((a) =>
    h("span", { class: "acct-chip", title: `${PLATFORM_NAMES[a.platform]} · ${(ACCOUNT_STATUS[a.status] || [a.status])[0]}` },
      h("span", { class: "mono-badge " + a.platform }, PLATFORM_MONO[a.platform]), a.label)));
}

function scheduleText(cfg) {
  const win = `${hourLabel(cfg.window_start)}–${hourLabel(cfg.window_end % 24)}`;
  return cfg.schedule_mode === "random"
    ? `${cfg.posts_min === cfg.posts_max ? cfg.posts_min : `${cfg.posts_min}–${cfg.posts_max}`}/day, random · ${win}`
    : `${cfg.posts_per_day}/day, evenly spaced · ${win}`;
}

async function pageCampaigns(root, token) {
  const list = await GET("/api/campaigns");
  if (isStale(token)) return;
  const newBtn = h("a", { class: "btn primary", href: "#/campaigns/new" }, icon("plus"), "New campaign");
  const tableWrap = h("div");

  function fill(list) {
    tableWrap.replaceChildren(list.length ? h("table", { class: "table" },
      h("thead", {}, h("tr", {}, h("th", { style: "width:56px" }, "Active"), h("th", {}, "Campaign"), h("th", {}, "Posts to"),
        h("th", {}, "Schedule"), h("th", {}, "Next post"), h("th", { class: "num" }, "Ready"), h("th", { class: "num" }, "Posted"), h("th", {}))),
      h("tbody", {}, list.map((c) => {
        const cfg = c.config, n = c.counts;
        return h("tr", { class: "clickable", onclick: (e) => { if (!e.target.closest("button, label")) location.hash = `#/campaigns/${c.id}`; } },
          h("td", {}, h("label", { class: "switch" }, h("input", { type: "checkbox", checked: !!c.enabled, "aria-label": "Active", onchange: async (e) => {
            await attempt(() => api("PUT", `/api/campaigns/${c.id}`, { enabled: e.target.checked }), e.target.checked ? "Campaign activated" : "Campaign paused");
          } }), h("span"))),
          h("td", {}, h("div", { class: "title-cell" }, c.name), h("div", { class: "muted small" }, cfg.niche || "No niche set")),
          h("td", {}, accountChips(c.accounts)),
          h("td", { class: "muted small" }, scheduleText(cfg)),
          h("td", {}, c.enabled && c.next_post_at ? when(c.next_post_at) : h("span", { class: "muted" }, "—")),
          h("td", { class: "num" }, (n.ready || 0) + (n.approved || 0) + (n.needs_review ? ` (+${n.needs_review} review)` : "")),
          h("td", { class: "num" }, (n.posted || 0) + (n.partial || 0)),
          h("td", { class: "num" }, h("button", { class: "btn sm", onclick: async () => {
            await attempt(() => api("POST", `/api/campaigns/${c.id}/generate`, {}), "Video queued for generation");
          } }, "Generate now")));
      })))
      : emptyState("No campaigns yet", "Pick a ready-made workflow or build your own. Each campaign can post to several accounts.",
          h("a", { class: "btn primary", href: "#/campaigns/new" }, "Create your first campaign")));
  }
  root.replaceChildren(pageHead("Campaigns", "Each campaign is a content series with its own prompt, look, accounts and schedule. Run as many as you like at once.", [newBtn]), card(null, tableWrap));
  fill(list);
  return { refresh: async () => { if (!document.activeElement || document.activeElement === document.body) { try { fill(await GET("/api/campaigns")); } catch {} } } };
}

/* ---------- new campaign: pick a workflow ---------- */

async function pageCampaignNew(root, presetKey, token) {
  if (presetKey) return pageCampaignEdit(root, "new", token, presetKey);
  const presets = await GET("/api/presets");
  if (isStale(token)) return;
  const cards = presets.map((p) => h("a", { class: "preset", href: `#/campaigns/new/${p.key}` },
    h("div", { class: "preset-name" }, p.name),
    h("div", { class: "preset-tag" }, p.tagline),
    h("dl", { class: "kv preset-kv" },
      h("dt", {}, "Length"), h("dd", {}, `${p.config.duration}s · ${p.config.scenes} scenes`),
      h("dt", {}, "Schedule"), h("dd", {}, scheduleText(p.config)),
      h("dt", {}, p.config.series_bible ? "Format" : "Topics"),
      h("dd", {}, p.config.series_bible ? "Ongoing episodes" : p.config.topics.length ? `${p.config.topics.length} ready to go` : "Model picks")),
    h("span", { class: "preset-cta" }, "Use this workflow ", icon("back"))));
  root.replaceChildren(
    pageHead("New campaign", "Start from a ready-made workflow — every setting is filled in. You only choose which accounts it posts to.", null, ["#/campaigns", "Campaigns"]),
    h("div", { class: "preset-grid" }, cards,
      h("a", { class: "preset blank", href: "#/campaigns/new/blank" },
        h("div", { class: "preset-name" }, "Start from scratch"),
        h("div", { class: "preset-tag" }, "Your own niche, prompt and look. Every option is editable."),
        h("span", { class: "preset-cta" }, "Build your own ", icon("back")))));
}

/* ---------- form helpers ---------- */

function section(title, desc, ...fields) {
  return h("div", { class: "form-section" }, h("header", {}, h("h3", {}, title), desc ? h("p", {}, desc) : null), h("div", { class: "fields" }, fields));
}
function field(label, control, help, attrs) {
  const id = control.id || (control.id = "f" + Math.random().toString(36).slice(2, 8));
  return h("div", Object.assign({ class: "field" }, attrs || {}), h("label", { for: id }, label), control, help ? h("div", { class: "help" }, help) : null);
}
function input(name, value, attrs) { return h("input", Object.assign({ class: "input", name, value: value ?? "" }, attrs || {})); }
function select(name, value, options) {
  return h("select", { class: "input", name }, options.map(([v, l]) => h("option", { value: String(v), selected: String(v) === String(value) }, l)));
}
function checkbox(name, checked, title, desc) {
  return h("label", { class: "check" }, h("input", { type: "checkbox", name, checked: !!checked }), h("span", {}, h("div", { class: "t" }, title), desc ? h("div", { class: "d" }, desc) : null));
}
function chips(name, values, options) {
  return h("div", { class: "chips", role: "group" }, options.map(([v, l]) =>
    h("label", { class: "chip" }, h("input", { type: "checkbox", name, value: String(v), checked: values.map(String).includes(String(v)) }), h("span", {}, l))));
}
function withSuffix(control, suffix) { return h("div", { class: "input-group" }, control, h("span", { class: "suffix" }, suffix)); }

const HOURS = Array.from({ length: 25 }, (_, i) => [i, i === 24 ? "Midnight (end of day)" : hourLabel(i)]);
const DAYS = [[0, "Mon"], [1, "Tue"], [2, "Wed"], [3, "Thu"], [4, "Fri"], [5, "Sat"], [6, "Sun"]];

/* ---------- campaign form ---------- */

async function pageCampaignEdit(root, idParam, token, presetKey) {
  const isNew = idParam === "new";
  const [prompts, defaults, accounts, camp, preset] = await Promise.all([
    GET("/api/prompts"), GET("/api/campaigns/defaults"), GET("/api/accounts"),
    isNew ? null : GET(`/api/campaigns/${idParam}`).catch(() => null),
    isNew && presetKey && presetKey !== "blank" ? api("POST", `/api/presets/${presetKey}/apply`).catch(() => null) : null]);
  if (isStale(token)) return;
  if (!isNew && !camp) { root.replaceChildren(emptyState("Campaign not found", "", h("a", { class: "btn", href: "#/campaigns" }, "Back"))); return; }
  // A preset may have just created its prompt, so re-read prompts.
  const promptList = preset ? await GET("/api/prompts") : prompts;
  if (isStale(token)) return;
  const cfg = camp ? camp.config : preset ? preset.config : { ...defaults, prompt_id: promptList[0] && promptList[0].id };
  const showWhen = (name, values) => ({ dataset: { showName: name, showValues: values.join(",") } });

  const byPlatform = Object.keys(PLATFORM_NAMES).map((p) => [p, accounts.filter((a) => a.platform === p)]).filter(([, l]) => l.length);
  const accountPicker = accounts.length
    ? h("div", { class: "acct-pick" }, byPlatform.map(([p, list]) => h("div", { class: "acct-group" },
        h("div", { class: "acct-group-title" }, PLATFORM_NAMES[p]),
        list.map((a) => h("label", { class: "check acct-option" },
          h("input", { type: "checkbox", name: "accounts", value: String(a.id), checked: cfg.accounts.includes(a.id) }),
          h("span", { class: "grow" }, h("div", { class: "t" }, a.label), a.campaigns.length ? h("div", { class: "d" }, "Also used by ", a.campaigns.filter((n) => !camp || n !== camp.name).join(", ") || "this campaign") : null),
          pill(ACCOUNT_STATUS, a.status))))),
        h("a", { class: "btn sm", href: "#/accounts", style: "align-self:flex-start" }, icon("plus"), "Add another account"))
    : h("div", { class: "note-box" }, "You haven't added any accounts yet. ", h("a", { href: "#/accounts" }, "Add accounts"), " first — you can save this campaign now and choose accounts later.");

  const modeSeg = h("div", { class: "seg", role: "radiogroup" }, [["random", "Random times"], ["even", "Evenly spaced"]].map(([v, l]) =>
    h("label", { class: "seg-opt" }, h("input", { type: "radio", name: "schedule_mode", value: v, checked: cfg.schedule_mode === v }), h("span", {}, l))));

  const upcoming = camp && camp.enabled && camp.upcoming.length
    ? h("div", { class: "note-box" }, h("strong", {}, "Coming up: "), camp.upcoming.slice(0, 6).map(when).join("  ·  "),
        cfg.schedule_mode === "random" ? h("div", { class: "muted small", style: "margin-top:4px" }, "Random times are drawn one day at a time, so only the current day's plan is shown.") : null)
    : null;

  const form = h("form", { onsubmit: (e) => e.preventDefault() },
    section("Basics", "Name the series and describe what it's about. The niche steers every script.",
      field("Campaign name", input("name", camp ? camp.name : preset ? preset.name : "", { placeholder: "e.g. Myths at Midnight", required: true })),
      field("Niche", input("niche", cfg.niche, { placeholder: "e.g. astronomy and space exploration" }), "One phrase describing the audience and subject."),
      checkbox("enabled", camp ? camp.enabled : isNew, "Active", "When autopilot is running, active campaigns generate and post on schedule.")),

    section("Accounts", "Where this campaign posts. Pick any mix of accounts across platforms; each account can belong to several campaigns.",
      accountPicker),

    section("Content", "Which prompt to use and what to talk about.",
      h("div", { class: "field" },
        h("label", { for: "f-prompt" }, "Prompt"),
        h("div", { class: "input-group" },
          h("select", { class: "input", name: "prompt_id", id: "f-prompt" }, promptList.map((p) => h("option", { value: String(p.id), selected: p.id === cfg.prompt_id }, p.name))),
          h("a", { class: "btn", href: "#/prompts" }, "Edit prompts"))),
      field("Topics", h("textarea", { class: "input", name: "topics", rows: 6, placeholder: "One topic per line — used in order, then repeated.\nLeave empty to let the model pick fresh topics within the niche.", value: cfg.topics.join("\n") }),
        cfg.topics.length ? `${cfg.topics.length} topics. Recent titles are always passed to the model to avoid repeats.` : "Optional. Recent titles are always passed to the model to avoid repeats."),
      field("Story world", h("textarea", { class: "input", name: "series_bible", rows: cfg.series_bible ? 8 : 3, value: cfg.series_bible,
        placeholder: "Optional. Describe a setting, characters and a central mystery to turn this campaign into an ongoing series — each video becomes the next episode." }),
        "When filled in, previous episodes are sent to the model so the story continues."),
      h("div", { class: "field-row" },
        field("Target length", withSuffix(input("duration", cfg.duration, { type: "number", min: 10, max: 170, class: "input narrow" }), "seconds")),
        field("Scenes", withSuffix(input("scenes", cfg.scenes, { type: "number", min: 2, max: 12, class: "input narrow" }), "images per video"))),
      field("Extra hashtags", input("extra_hashtags", cfg.extra_hashtags, { placeholder: "#space #science" }), "Added to every post, after the model's own hashtags.")),

    section("Look and sound", "Image style, captions and background music.",
      field("Visual style", input("visual_style", cfg.visual_style), "Appended to every image prompt."),
      h("div", { class: "field-row" },
        field("Words per caption", select("caption_words", cfg.caption_words, [[1, "1 word"], [2, "2 words"], [3, "3 words"], [4, "4 words"]])),
        field("Caption position", select("caption_position", cfg.caption_position, [["middle", "Middle of frame"], ["lower", "Lower third"]]))),
      checkbox("caption_uppercase", cfg.caption_uppercase, "Uppercase captions"),
      field("Music folder", input("music_dir", cfg.music_dir, { placeholder: "C:\\Users\\you\\Music\\Clipper" }), "Optional. A random track from this folder plays under the voice. Use music you have rights to."),
      field("Music volume", withSuffix(input("music_volume", Math.round(cfg.music_volume * 100), { type: "number", min: 0, max: 100, class: "input narrow" }), "%"))),

    section("Schedule", "When to post. Random times look more natural; evenly spaced is more predictable. Each post goes to every selected account.",
      h("div", { class: "field" }, h("div", { class: "label" }, "Timing"), modeSeg),
      h("div", Object.assign({ class: "field-row" }, showWhen("schedule_mode", ["random"])),
        field("Posts per day", h("div", { class: "input-group" },
          input("posts_min", cfg.posts_min, { type: "number", min: 1, max: 12, class: "input narrow", "aria-label": "Minimum posts per day" }),
          h("span", { class: "suffix" }, "to"),
          input("posts_max", cfg.posts_max, { type: "number", min: 1, max: 12, class: "input narrow", "aria-label": "Maximum posts per day" })), "A new random count is picked each day."),
        field("Minimum gap", withSuffix(input("min_gap_minutes", cfg.min_gap_minutes, { type: "number", min: 0, max: 720, class: "input narrow" }), "minutes between posts"))),
      h("div", Object.assign({ class: "field-row" }, showWhen("schedule_mode", ["even"])),
        field("Posts per day", withSuffix(input("posts_per_day", cfg.posts_per_day, { type: "number", min: 1, max: 12, class: "input narrow" }), "per day")),
        field("Random offset", withSuffix(input("jitter_minutes", cfg.jitter_minutes, { type: "number", min: 0, max: 120, class: "input narrow" }), "± minutes"))),
      h("div", { class: "field-row" },
        field("Window opens", select("window_start", cfg.window_start, HOURS.slice(0, 24))),
        field("Window closes", select("window_end", cfg.window_end, HOURS.slice(1)))),
      h("div", { class: "field" }, h("div", { class: "label" }, "Days"), chips("days", cfg.days, DAYS)),
      field("YouTube visibility", select("youtube_visibility", cfg.youtube_visibility, [["public", "Public"], ["unlisted", "Unlisted"], ["private", "Private"]])),
      upcoming),

    section("Automation", "How much Clipper does without you.",
      checkbox("review", cfg.review, "Hold videos for my approval", "Generated videos wait in the Library until you approve them. Turn off for fully hands-off posting."),
      field("Buffer", withSuffix(input("buffer", cfg.buffer, { type: "number", min: 1, max: 20, class: "input narrow" }), "videos generated ahead"), "Keeps this many videos ready so a slow render never delays a post."),
      checkbox("ai_label", cfg.ai_label, "Label posts as AI-generated", "Ticks each platform's synthetic-content disclosure. YouTube, TikTok and Instagram require it for realistic AI media.")),

    h("div", { class: "sticky-save" },
      camp ? h("button", { class: "btn danger", type: "button", onclick: async () => {
        if (!confirm(`Delete “${camp.name}”? Its videos stay in the Library.`)) return;
        if (await attempt(() => api("DELETE", `/api/campaigns/${camp.id}`), "Campaign deleted")) location.hash = "#/campaigns";
      } }, "Delete") : null,
      h("span", { class: "grow" }),
      h("a", { class: "btn", href: isNew ? "#/campaigns/new" : "#/campaigns" }, isNew ? "Back" : "Cancel"),
      h("button", { class: "btn primary", type: "submit", onclick: save }, isNew ? "Create campaign" : "Save changes")));

  function syncVisibility() {
    form.querySelectorAll("[data-show-name]").forEach((el) => {
      const val = (form.querySelector(`[name="${el.dataset.showName}"]:checked`) || {}).value;
      el.hidden = !el.dataset.showValues.split(",").includes(val);
    });
  }
  form.addEventListener("change", syncVisibility);

  async function save() {
    const fd = new FormData(form);
    const name = String(fd.get("name") || "").trim();
    if (!name) { toast("Give the campaign a name", "error"); form.elements.name.focus(); return; }
    const num = (k) => Number(fd.get(k));
    const body = {
      name,
      enabled: form.elements.enabled.checked,
      config: {
        ...cfg,
        niche: fd.get("niche").trim(),
        accounts: fd.getAll("accounts").map(Number),
        prompt_id: Number(fd.get("prompt_id")) || null,
        topics: fd.get("topics").split("\n").map((t) => t.trim()).filter(Boolean),
        series_bible: fd.get("series_bible").trim(),
        duration: num("duration"), scenes: num("scenes"),
        extra_hashtags: fd.get("extra_hashtags"),
        visual_style: fd.get("visual_style"),
        caption_words: num("caption_words"), caption_position: fd.get("caption_position"),
        caption_uppercase: form.elements.caption_uppercase.checked,
        music_dir: fd.get("music_dir").trim(), music_volume: num("music_volume") / 100,
        schedule_mode: fd.get("schedule_mode"),
        posts_min: num("posts_min"), posts_max: num("posts_max"), min_gap_minutes: num("min_gap_minutes"),
        posts_per_day: num("posts_per_day"), jitter_minutes: num("jitter_minutes"),
        window_start: num("window_start"), window_end: num("window_end"),
        days: fd.getAll("days").map(Number),
        youtube_visibility: fd.get("youtube_visibility"),
        review: form.elements.review.checked, buffer: num("buffer"), ai_label: form.elements.ai_label.checked,
      },
    };
    const c = body.config;
    if (c.window_end <= c.window_start) { toast("The posting window must close after it opens", "error"); return; }
    if (c.schedule_mode === "random" && c.posts_max < c.posts_min) { toast("Maximum posts per day must be at least the minimum", "error"); return; }
    if (!c.days.length) { toast("Pick at least one posting day", "error"); return; }
    if (!c.accounts.length && body.enabled && !confirm("No accounts are selected, so this campaign will make videos but not post them. Save anyway?")) return;
    const saved = await attempt(() => isNew ? api("POST", "/api/campaigns", body) : api("PUT", `/api/campaigns/${camp.id}`, body), isNew ? "Campaign created" : "Changes saved");
    if (saved && isNew) location.hash = `#/campaigns/${saved.id}`;
    else if (saved) route();
  }

  const actions = camp ? [h("button", { class: "btn", type: "button", onclick: async () => {
    await attempt(() => api("POST", `/api/campaigns/${camp.id}/generate`, {}), "Video queued — watch progress in the Library");
  } }, icon("bolt"), "Generate a video now")] : null;
  const sub = preset ? `Ready-made workflow: ${preset.name}. Everything is filled in — pick your accounts and create it.`
    : isNew ? "Set up a content series. You can change everything later." : null;

  root.replaceChildren(pageHead(isNew ? (preset ? preset.name : "New campaign") : camp.name, sub, actions, isNew ? ["#/campaigns/new", "Workflows"] : ["#/campaigns", "Campaigns"]), form);
  syncVisibility();
}

/* ============================================================
   Library
   ============================================================ */

const LIB_FILTERS = [
  ["all", "All", ""], ["review", "Needs review", "needs_review"], ["ready", "Ready", "ready,approved"],
  ["progress", "In progress", "queued,generating,posting,retrying"], ["posted", "Posted", "posted,partial,check"],
  ["failed", "Failed", "failed,post_failed,rejected"],
];
const libState = { filter: "all", campaign: "" };

async function pageLibrary(root, token) {
  const camps = await GET("/api/campaigns");
  if (isStale(token)) return;
  const grid = h("div");
  const seg = h("div", { class: "seg", role: "tablist" });
  const campSel = h("select", { class: "input", style: "width:auto", "aria-label": "Campaign", onchange: (e) => { libState.campaign = e.target.value; load(); } },
    h("option", { value: "" }, "All campaigns"), camps.map((c) => h("option", { value: String(c.id), selected: String(c.id) === libState.campaign }, c.name)));
  const count = h("span", { class: "muted small" });

  function renderSeg() {
    seg.replaceChildren(...LIB_FILTERS.map(([key, label]) => h("button", { type: "button", role: "tab", class: libState.filter === key ? "on" : "", "aria-selected": String(libState.filter === key),
      onclick: () => { libState.filter = key; renderSeg(); load(); } }, label)));
  }

  async function load() {
    const status = LIB_FILTERS.find((f) => f[0] === libState.filter)[2];
    const q = new URLSearchParams({ status, campaign_id: libState.campaign || 0 });
    let vids;
    try { vids = await GET(`/api/videos?${q}`); } catch { return; }
    count.textContent = `${vids.length} video${vids.length === 1 ? "" : "s"}`;
    grid.replaceChildren(vids.length ? h("div", { class: "vgrid" }, vids.map(videoCard))
      : card(null, emptyState("Nothing here", libState.filter === "all" ? "Generate a video from a campaign to get started." : "No videos match this filter.")));
  }

  renderSeg();
  root.replaceChildren(pageHead("Library", "Every video Clipper has made. Open one to preview, edit, approve or post it."),
    h("div", { class: "toolbar" }, seg, campSel, h("span", { class: "grow" }), count), grid);
  await load();
  return { refresh: load };
}

function videoCard(v) {
  return h("button", { class: "vcard", type: "button", onclick: () => openVideo(v.id) },
    h("div", { class: "vthumb" },
      v.thumb_url ? h("img", { src: v.thumb_url, alt: "", loading: "lazy" }) : h("span", { class: "small" }, v.status === "generating" ? "Rendering…" : "No preview"),
      pill(VIDEO_STATUS, v.status),
      v.duration ? h("span", { class: "dur" }, `0:${String(Math.round(v.duration)).padStart(2, "0")}`) : null),
    h("div", { class: "vmeta" },
      h("div", { class: "t" }, v.title || (v.status === "failed" ? "Generation failed" : "Writing script…")),
      h("div", { class: "m" }, `#${v.id} · ${rel(v.created_at)}`)));
}

/* ---------- video drawer ---------- */

let drawerTimer = null;

function closeDrawer() {
  clearInterval(drawerTimer);
  document.getElementById("drawer-root").replaceChildren();
  document.removeEventListener("keydown", escClose);
}
function escClose(e) { if (e.key === "Escape") closeDrawer(); }

async function openVideo(id) {
  closeDrawer();
  const rootEl = document.getElementById("drawer-root");
  const body = h("div", { class: "drawer-body" }, h("div", { class: "empty" }, "Loading…"));
  const title = h("h2", {}, `Video #${id}`);
  const statusSlot = h("span");
  rootEl.replaceChildren(h("div", { class: "scrim", onclick: closeDrawer }),
    h("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": "Video details" },
      h("div", { class: "drawer-head" }, statusSlot, title, h("button", { class: "btn ghost icon-only", "aria-label": "Close", onclick: closeDrawer }, icon("x"))), body));
  document.addEventListener("keydown", escClose);

  let last = "";
  async function load(force) {
    let v;
    try { v = await GET(`/api/videos/${id}`); } catch (e) { body.replaceChildren(emptyState("Video not found", e.message)); clearInterval(drawerTimer); return; }
    const sig = JSON.stringify([v.status, v.updated_at, v.posts]);
    const editing = body.contains(document.activeElement) && /INPUT|TEXTAREA/.test(document.activeElement.tagName);
    if (!force && (sig === last || editing)) return;
    last = sig;
    statusSlot.replaceChildren(pill(VIDEO_STATUS, v.status));
    title.textContent = v.title || `Video #${v.id}`;
    body.replaceChildren(renderVideo(v, load));
  }
  await load(true);
  drawerTimer = setInterval(() => !document.hidden && load(false), 3000);
}

function renderVideo(v, reload) {
  const act = (action, payload, msg) => async () => {
    const r = await attempt(() => api("POST", `/api/videos/${v.id}/${action}`, payload || {}), msg);
    if (r) { reload(true); refreshShell(); if (current && current.refresh) current.refresh(); }
  };
  const working = ["queued", "generating"].includes(v.status);

  const left = h("div", {},
    v.video_url ? h("video", { class: "player", src: v.video_url, controls: true, preload: "metadata", playsinline: true })
      : h("div", { class: "player-empty" }, working ? h("div", {}, h("div", { style: "font-weight:550;color:var(--text)" }, v.status === "queued" ? "Queued" : "Generating"), h("div", { class: "small" }, v.status === "generating" ? (v.error || "Starting") : "Waiting for the generator")) : "No video file"),
    h("div", { class: "stack", style: "gap:8px;margin-top:12px" },
      v.status === "needs_review" ? h("button", { class: "btn primary", onclick: act("approve", null, "Approved — it will post at the next slot") }, icon("check"), "Approve") : null,
      v.status === "needs_review" ? h("button", { class: "btn", onclick: act("reject", null, "Rejected") }, "Reject") : null,
      v.video_url && !["posting", "posted"].includes(v.status) ? h("button", { class: v.status === "needs_review" ? "btn" : "btn primary", onclick: () => {
        if (!v.targets.length) { toast("This campaign has no accounts selected", "error"); return; }
        if (confirm(`Post this video now to ${v.targets.map((a) => `${a.label} (${PLATFORM_NAMES[a.platform]})`).join(", ")}?`)) act("post", null, "Posting started")();
      } }, icon("upload"), "Post now") : null,
      v.video_url ? h("a", { class: "btn", href: v.video_url, download: `clipper-${v.id}.mp4` }, icon("download"), "Download") : null,
      !working ? h("button", { class: "btn", onclick: () => { if (confirm("Throw this version away and generate a new one?")) act("regenerate", null, "Regenerating")(); } }, icon("refresh"), "Regenerate") : null,
      h("button", { class: "btn danger", onclick: async () => {
        if (!confirm("Delete this video and its file?")) return;
        if (await attempt(() => api("DELETE", `/api/videos/${v.id}`), "Video deleted")) { closeDrawer(); if (current && current.refresh) current.refresh(); }
      } }, "Delete")));

  const fTitle = h("input", { class: "input", value: v.title, maxlength: 100 });
  const fDesc = h("textarea", { class: "input", rows: 3, value: v.description });
  const fTags = h("input", { class: "input", value: v.hashtags.map((t) => "#" + t).join(" ") });

  const postRows = v.targets.length ? v.targets.map((a) => {
    const post = v.posts.find((x) => x.account_id === a.id);
    const st = post ? post.status : "pending";
    return h("tr", {},
      h("td", { class: "title-cell" }, h("span", { class: "mono-badge " + a.platform, style: "margin-right:8px" }, PLATFORM_MONO[a.platform]), a.label),
      h("td", {}, post ? pill(POST_STATUS, st) : h("span", { class: "pill" }, "Not posted"), post && post.attempts ? h("span", { class: "muted small" }, `  ${post.attempts} attempt${post.attempts > 1 ? "s" : ""}`) : null),
      h("td", { class: "small" }, post && post.url ? h("a", { href: post.url, target: "_blank", rel: "noopener" }, "Open ", icon("external"))
        : post && post.error ? h("span", { class: st === "unconfirmed" ? "muted" : "", style: st === "failed" ? "color:var(--red)" : "" }, post.error) : h("span", { class: "muted" }, "—")),
      h("td", { class: "num" },
        st === "unconfirmed" ? h("button", { class: "btn sm", onclick: act("mark_posted", { account_id: a.id }, "Marked as posted") }, "It posted") : null,
        v.video_url && ["failed", "unconfirmed", "pending"].includes(st) && post ? h("button", { class: "btn sm", style: "margin-left:6px", onclick: () => {
          if (st !== "unconfirmed" || confirm("Retrying may create a duplicate if the first attempt actually went through. Retry?")) act("post", { accounts: [a.id] }, "Retry started")();
        } }, "Retry") : null));
  }) : [h("tr", {}, h("td", { class: "muted" }, "This campaign has no accounts selected."))];

  const right = h("div", {},
    v.status === "failed" && v.error ? h("div", { class: "error-box", style: "margin-bottom:16px" }, v.error) : null,
    h("div", { class: "stack", style: "gap:12px" },
      field("Title", fTitle), field("Description", fDesc), field("Hashtags", fTags),
      h("div", { class: "row" }, h("button", { class: "btn", onclick: async () => {
        const r = await attempt(() => api("PUT", `/api/videos/${v.id}`, { title: fTitle.value, description: fDesc.value, hashtags: fTags.value }), "Saved");
        if (r) { document.activeElement.blur(); reload(true); }
      } }, "Save text"), h("span", { class: "muted small" }, "Edits apply to posts that haven't gone out yet."))),
    h("div", { class: "section-title" }, "Accounts"),
    h("div", { class: "card" }, h("table", { class: "table" }, h("tbody", {}, postRows))),
    h("div", { class: "section-title" }, "Details"),
    h("dl", { class: "kv" },
      h("dt", {}, "Campaign"), h("dd", {}, v.campaign_name),
      h("dt", {}, "Topic"), h("dd", {}, v.topic || "—"),
      h("dt", {}, "Length"), h("dd", {}, v.duration ? `${v.duration}s` : "—"),
      h("dt", {}, "Created"), h("dd", {}, when(v.created_at)),
      h("dt", {}, "Posted"), h("dd", {}, v.posted_at ? when(v.posted_at) : "—")),
    v.script ? h("div", {}, h("div", { class: "section-title" }, "Script"),
      v.script.scenes.map((s, i) => h("div", { class: "scene" }, h("div", { class: "n" }, `Scene ${i + 1}`), h("div", {}, s.narration), h("div", { class: "v" }, "Visual: ", s.visual)))) : null);

  return h("div", { class: "drawer-split" }, left, right);
}

/* ============================================================
   Prompts
   ============================================================ */

async function pagePrompts(root, pid, token) {
  const prompts = await GET("/api/prompts");
  if (isStale(token)) return;
  const selected = pid === "new" ? null : prompts.find((p) => String(p.id) === pid) || (pid ? null : prompts[0]);
  if (pid && pid !== "new" && !selected) { location.hash = "#/prompts"; return; }

  const list = h("div", { class: "plist" }, prompts.map((p) =>
    h("a", { href: `#/prompts/${p.id}`, class: selected && selected.id === p.id ? "active" : "" }, p.name)));

  const name = h("input", { class: "input", value: selected ? selected.name : "", placeholder: "e.g. Myth vs fact" });
  const body = h("textarea", { class: "input code", rows: 12, value: selected ? selected.body : "", placeholder: "Describe the kind of video you want. Use {niche} where the campaign's niche should go." });
  const insertVar = (v) => () => {
    const [s, e] = [body.selectionStart, body.selectionEnd];
    body.setRangeText(v, s, e, "end");
    body.focus();
  };

  const tNiche = h("input", { class: "input", placeholder: "Niche for the test, e.g. deep sea creatures" });
  const tTopic = h("input", { class: "input", placeholder: "Optional topic" });
  const result = h("div");
  const runBtn = h("button", { class: "btn", onclick: async () => {
    runBtn.disabled = true;
    runBtn.textContent = "Writing…";
    result.replaceChildren(h("div", { class: "note-box" }, "Asking the local model. This can take a minute on first load."));
    try {
      const r = await api("POST", "/api/prompts/test", { body: body.value, niche: tNiche.value, topic: tTopic.value });
      result.replaceChildren(h("div", { class: "stack", style: "gap:10px" },
        h("div", {}, h("div", { class: "muted small" }, "Title"), h("div", { style: "font-weight:600;font-size:15px" }, r.title)),
        h("div", {}, h("div", { class: "muted small" }, "Description"), h("div", {}, r.description)),
        h("div", { class: "muted small" }, r.hashtags.map((t) => "#" + t).join(" ")),
        h("div", {}, r.scenes.map((s, i) => h("div", { class: "scene" }, h("div", { class: "n" }, `Scene ${i + 1}`), h("div", {}, s.narration), h("div", { class: "v" }, "Visual: ", s.visual))))));
    } catch (e) {
      result.replaceChildren(h("div", { class: "error-box" }, e.message));
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = "Run test";
    }
  } }, "Run test");

  const editor = (selected || pid === "new") ? h("div", { class: "stack" },
    card(null, h("div", { class: "card-body stack" },
      field("Name", name),
      h("div", { class: "field" },
        h("label", {}, "Instructions"),
        body,
        h("div", { class: "help row", style: "flex-wrap:wrap" }, "Insert:", h("button", { class: "var", type: "button", onclick: insertVar("{niche}") }, "{niche}"),
          h("button", { class: "var", type: "button", onclick: insertVar("{topic}") }, "{topic}"),
          h("span", {}, "· Output format, length, scene count and repeat-avoidance are added automatically — write only the creative direction."))),
    ), h("div", { class: "card-foot" },
      selected ? h("button", { class: "btn danger", onclick: async () => {
        if (!confirm(`Delete “${selected.name}”? Campaigns using it fall back to the first prompt in this list.`)) return;
        if (await attempt(() => api("DELETE", `/api/prompts/${selected.id}`), "Prompt deleted")) location.hash = "#/prompts";
      } }, "Delete") : null,
      h("span", { class: "grow" }),
      h("button", { class: "btn primary", onclick: async () => {
        if (!name.value.trim() || !body.value.trim()) { toast("Name and instructions are required", "error"); return; }
        const payload = { name: name.value.trim(), body: body.value };
        const r = await attempt(() => selected ? api("PUT", `/api/prompts/${selected.id}`, payload) : api("POST", "/api/prompts", payload), "Prompt saved");
        if (r) { const target = `#/prompts/${r.id}`; if (location.hash === target) route(); else location.hash = target; }
      } }, "Save prompt"))),
    card("Test this prompt", h("div", { class: "card-body stack", style: "gap:12px" },
      h("div", { class: "field-row" }, tNiche, tTopic), h("div", {}, runBtn), result)))
    : card(null, emptyState("No prompt selected", "Create one to get started."));

  root.replaceChildren(
    pageHead("Prompts", "Reusable creative instructions. Campaigns pick one; you can test it here before it goes live.",
      [h("a", { class: "btn primary", href: "#/prompts/new" }, icon("plus"), "New prompt")]),
    h("div", { class: "split" }, card(null, list), editor));
}

/* ============================================================
   Accounts
   ============================================================ */

async function pageAccounts(root, token) {
  const wrap = h("div", { class: "stack" });
  const addPlatform = h("select", { class: "input", style: "width:auto", "aria-label": "Platform" },
    Object.entries(PLATFORM_NAMES).map(([k, n]) => h("option", { value: k }, n)));
  const addLabel = h("input", { class: "input", placeholder: "Name, e.g. Mythology channel", "aria-label": "Account name", style: "max-width:280px" });
  const addForm = h("form", { class: "row", style: "flex-wrap:wrap", onsubmit: async (e) => {
    e.preventDefault();
    const r = await attempt(() => api("POST", "/api/accounts", { platform: addPlatform.value, label: addLabel.value }), "Account added — click Connect to sign in");
    if (r) { addLabel.value = ""; load(); }
  } }, addPlatform, addLabel, h("button", { class: "btn primary", type: "submit" }, icon("plus"), "Add account"));

  async function load() {
    let accts;
    try { accts = await GET("/api/accounts"); } catch { return; }
    if (isStale(token)) return;
    const groups = Object.keys(PLATFORM_NAMES).map((p) => [p, accts.filter((a) => a.platform === p)]);
    wrap.replaceChildren(...(accts.length ? groups.filter(([, l]) => l.length).map(([p, list]) => card(`${PLATFORM_NAMES[p]} · ${list.length}`,
      h("div", {}, list.map((a) => {
        const busy = ["checking", "login_open"].includes(a.status);
        const run = (action, msg) => async () => { await attempt(() => api("POST", `/api/accounts/${a.id}/${action}`), msg); setTimeout(load, 600); };
        return h("div", { class: "list-item acct-row" },
          h("div", { class: "acct-logo" }, PLATFORM_MONO[a.platform]),
          h("div", { class: "grow", style: "min-width:0" },
            h("div", { class: "row" }, h("span", { style: "font-weight:600" }, a.label),
              h("button", { class: "btn ghost sm", "aria-label": "Rename", onclick: async () => {
                const label = prompt("Rename account", a.label);
                if (label && label.trim()) { await attempt(() => api("PUT", `/api/accounts/${a.id}`, { label }), "Renamed"); load(); }
              } }, "Rename")),
            h("div", { class: "muted small" },
              `${a.posted} posted · ${a.posted_today} today`,
              a.campaigns.length ? ` · used by ${a.campaigns.join(", ")}` : " · not used by any campaign"),
            a.note ? h("div", { class: "muted small" }, a.note) : null),
          pill(ACCOUNT_STATUS, a.status),
          h("div", { class: "row" },
            h("button", { class: "btn sm", disabled: busy, onclick: run("check", "Checking sign-in…") }, "Check"),
            h("button", { class: "btn primary sm", disabled: busy, onclick: run("connect", "A browser window is opening — sign in, then close it") }, a.status === "connected" ? "Reconnect" : "Connect"),
            h("button", { class: "btn ghost sm danger", disabled: busy, onclick: async () => {
              if (!confirm(`Remove “${a.label}”? Its saved sign-in is deleted and it's removed from campaigns. Post history is kept.`)) return;
              await attempt(() => api("DELETE", `/api/accounts/${a.id}`), "Account removed"); load();
            } }, "Remove")));
      }))))
      : [card(null, emptyState("No accounts yet", "Add one above for each channel you want to post to. You can add several per platform."))]));
  }
  root.replaceChildren(
    pageHead("Accounts", "Add as many accounts as you like — several per platform is fine. Each one keeps its own sign-in."),
    card(null, h("div", { class: "card-body" }, addForm)),
    h("div", { class: "note-box", style: "margin:16px 0" },
      "Connect opens a normal browser window for that account only. Sign in as you usually do (including two-step verification), then close the window. ",
      "Each account's session lives in its own folder under data/browser_profiles — Clipper never stores passwords. ",
      "For YouTube, if one Google login owns several channels, switch to the right channel before closing the window; each account remembers its channel."),
    wrap);
  await load();
  return { refresh: load };
}

/* ============================================================
   Activity
   ============================================================ */

const actState = { level: "" };

async function pageActivity(root, token) {
  const seg = h("div", { class: "seg" });
  const listEl = h("div");
  function renderSeg() {
    seg.replaceChildren(...[["", "All"], ["info", "Info"], ["warn", "Warnings"], ["error", "Errors"]].map(([k, l]) =>
      h("button", { type: "button", class: actState.level === k ? "on" : "", onclick: () => { actState.level = k; renderSeg(); load(); } }, l)));
  }
  async function load() {
    let logs;
    try { logs = await GET(`/api/logs?level=${actState.level}`); } catch { return; }
    if (isStale(token)) return;
    listEl.replaceChildren(card(null, logs.length ? h("div", {}, logs.map(logLine)) : emptyState("Nothing logged", "")));
  }
  renderSeg();
  root.replaceChildren(pageHead("Activity", "A running log of generation, posting and scheduling."), h("div", { class: "toolbar" }, seg), listEl);
  await load();
  return { refresh: load };
}

/* ============================================================
   Settings
   ============================================================ */

async function pageSettings(root, token) {
  const s = await GET("/api/settings");
  if (isStale(token)) return;
  const models = h("datalist", { id: "llm-models" });
  const loadModels = async () => {
    try {
      const list = await GET("/api/llm/models");
      models.replaceChildren(...list.map((m) => h("option", { value: m })));
      toast(`${list.length} model${list.length === 1 ? "" : "s"} found`);
    } catch (e) { toast(e.message, "error"); }
  };

  const showWhen = (name, values) => ({ dataset: { showName: name, showValues: values.join(",") } });

  const form = h("form", { onsubmit: (e) => e.preventDefault() },
    section("Script model", "The local language model that writes titles, narration and image prompts.",
      field("Server", select("llm_provider", s.llm_provider, [["ollama", "Ollama"], ["openai", "OpenAI-compatible (LM Studio, llama.cpp, vLLM)"]])),
      field("Address", input("llm_url", s.llm_url), "Ollama: http://127.0.0.1:11434 · LM Studio: http://127.0.0.1:1234"),
      field("Model", h("div", { class: "input-group" }, input("llm_model", s.llm_model, { list: "llm-models" }), h("button", { class: "btn", type: "button", onclick: loadModels }, "List models")), "e.g. llama3.1:8b, qwen2.5:14b, mistral-nemo"),
      field("Creativity", withSuffix(input("llm_temperature", s.llm_temperature, { type: "number", min: 0, max: 2, step: 0.1, class: "input narrow" }), "temperature (0.7–1.0 works well)")),
      models),

    section("Images", "Where scene images come from.",
      field("Engine", select("image_engine", s.image_engine, [["comfyui", "ComfyUI"], ["a1111", "Stable Diffusion WebUI (AUTOMATIC1111 / Forge)"], ["cards", "Styled backgrounds (no image AI)"]])),
      field("Address", input("image_url", s.image_url), "ComfyUI: http://127.0.0.1:8188 · WebUI/Forge: http://127.0.0.1:7860 (start it with --api)", showWhen("image_engine", ["comfyui", "a1111"])),
      field("Checkpoint", input("comfy_checkpoint", s.comfy_checkpoint), "File name exactly as it appears in ComfyUI's models/checkpoints folder.", showWhen("image_engine", ["comfyui"])),
      field("Custom workflow", input("comfy_workflow_path", s.comfy_workflow_path, { placeholder: "Optional: path to an API-format workflow .json" }),
        "Use {{prompt}}, {{negative}}, {{seed}}, {{width}}, {{height}}, {{steps}} and {{checkpoint}} as placeholders.", showWhen("image_engine", ["comfyui"])),
      h("div", Object.assign({ class: "field-row" }, showWhen("image_engine", ["comfyui", "a1111"])),
        field("Width", input("image_width", s.image_width, { type: "number", step: 8 })), field("Height", input("image_height", s.image_height, { type: "number", step: 8 }))),
      field("Steps", input("image_steps", s.image_steps, { type: "number", min: 1, max: 150, class: "input narrow" }), null, showWhen("image_engine", ["comfyui", "a1111"])),
      field("Negative prompt", h("textarea", { class: "input", name: "negative_prompt", rows: 2, value: s.negative_prompt }), null, showWhen("image_engine", ["comfyui", "a1111"]))),

    section("Voice", "Text-to-speech for the narration.",
      field("Engine", select("tts_engine", s.tts_engine, [["piper", "Piper (recommended, local neural voices)"], ["system", "System voice (Windows SAPI / macOS / espeak)"], ["none", "No voiceover"]])),
      field("Piper voice", input("piper_model", s.piper_model, { placeholder: "C:\\Clipper\\voices\\en_US-ryan-high.onnx" }), "Path to a downloaded .onnx voice (keep its .onnx.json next to it).", showWhen("tts_engine", ["piper"])),
      field("Speaking speed", withSuffix(input("tts_speed", s.tts_speed, { type: "number", min: 0.5, max: 2, step: 0.05, class: "input narrow" }), "× (1.0 = natural)"), null, showWhen("tts_engine", ["piper", "system"]))),

    section("Video", "Rendering with ffmpeg.",
      h("div", { class: "field-row" }, field("ffmpeg", input("ffmpeg_path", s.ffmpeg_path)), field("ffprobe", input("ffprobe_path", s.ffprobe_path))),
      h("div", { class: "field-row" }, field("Caption font", input("caption_font", s.caption_font), "Any installed font name."), field("Frame rate", select("fps", s.fps, [[24, "24 fps"], [30, "30 fps"], [60, "60 fps"]])))),

    section("Posting", "How the browser behaves and how much Clipper may post.",
      field("Browser", select("browser_channel", s.browser_channel, [["chrome", "Google Chrome"], ["msedge", "Microsoft Edge"], ["chromium", "Built-in Chromium"]]), "Chrome or Edge is most reliable for signing in."),
      checkbox("headless", s.headless, "Post in the background", "Hide the browser window while posting. Some platforms behave differently when hidden — leave off if posts fail."),
      field("Daily safety cap", withSuffix(input("max_posts_per_account", s.max_posts_per_account, { type: "number", min: 1, max: 50, class: "input narrow" }), "posts per account per day"),
        "Extra posts wait until the next day. Keeps any one account from looking like a bot."),
      field("Parallel uploads", withSuffix(input("parallel_uploads", s.parallel_uploads, { type: "number", min: 1, max: 8, class: "input narrow" }), "accounts at once"),
        "How many accounts may upload at the same time. Each opens its own browser. Takes effect after restarting Clipper."),
      field("Clean up", withSuffix(input("delete_after_days", s.delete_after_days, { type: "number", min: 0, class: "input narrow" }), "days after posting (0 keeps files)"), "Deletes rendered files to save disk space. History stays."),
      checkbox("open_browser_on_start", s.open_browser_on_start, "Open this dashboard when Clipper starts")),

    h("div", { class: "sticky-save" }, h("span", { class: "grow" }), h("button", { class: "btn primary", type: "submit", onclick: save }, "Save settings")));

  function syncVisibility() {
    form.querySelectorAll("[data-show-name]").forEach((el) => {
      const ctl = form.elements[el.dataset.showName];
      el.hidden = !el.dataset.showValues.split(",").includes(ctl.value);
    });
  }
  form.addEventListener("change", syncVisibility);

  async function save() {
    const body = {};
    for (const el of form.elements) {
      if (!el.name) continue;
      body[el.name] = el.type === "checkbox" ? el.checked : el.value;
    }
    await attempt(() => api("PUT", "/api/settings", body), "Settings saved");
  }

  root.replaceChildren(pageHead("Settings", "Local AI engines, rendering and posting behaviour."), form);
  syncVisibility();
}

/* ============================================================
   Boot
   ============================================================ */

window.addEventListener("hashchange", () => { closeDrawer(); route(); });
refreshShell();
route();
