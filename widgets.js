"use strict";

/* ---------- helpers ---------- */

// Build DOM without innerHTML so third-party text can never inject markup.
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function safeUrl(u) {
  if (typeof u !== "string") return null;
  try {
    const url = new URL(u); // absolute URLs only
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch { return null; }
}

function link(text, href) {
  const safe = safeUrl(href);
  return safe ? h("a", { href: safe, target: "_blank", rel: "noopener noreferrer" }, text) : h("span", {}, text);
}

// JSON fetch with a small localStorage cache so repeat visits are fast and
// public APIs don't get hammered. Falls back to stale data when offline.
async function getJson(url, ttlMs = 10 * 60 * 1000) {
  const key = "cache:" + url;
  let cached = null;
  try { cached = JSON.parse(localStorage.getItem(key)); } catch {}
  if (cached && Date.now() - cached.t < ttlMs) return cached.v;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const v = await res.json();
    try { localStorage.setItem(key, JSON.stringify({ t: Date.now(), v })); } catch {}
    return v;
  } catch (e) {
    if (cached) return cached.v;
    throw e;
  }
}

function loading(body) { body.replaceChildren(h("p", { class: "muted" }, "Loading…")); }
function failed(body, e) { body.replaceChildren(h("p", { class: "err" }, "Couldn't load this widget. ", h("span", { class: "muted" }, e && e.message ? e.message : ""))); }

const WMO = {
  0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
  51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
  71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Showers", 81: "Showers", 82: "Heavy showers",
  95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm"
};
const WMO_ICON = (c) => c === 0 ? "☀️" : c <= 2 ? "⛅" : c === 3 ? "☁️" : c <= 48 ? "🌫️" : c <= 55 ? "🌦️" : c <= 65 ? "🌧️" : c <= 75 ? "❄️" : c <= 82 ? "🌦️" : "⛈️";

/* ---------- widget registry ---------- */
/* Each widget: { name, desc, wide, defaults(), render(body, ctx) -> optional cleanup }
   ctx = { config, save(), refresh() } — mutate ctx.config then call ctx.save(). */

const Widgets = {};

Widgets.clock = {
  name: "Clock", desc: "Time and date", defaults: () => ({}),
  render(body) {
    const time = h("div", { class: "big" });
    const date = h("div", { class: "muted" });
    body.replaceChildren(time, date);
    const tick = () => {
      const now = new Date();
      time.textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      date.textContent = now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }
};

Widgets.weather = {
  name: "Weather", desc: "Current conditions and 5-day forecast (Open-Meteo)",
  defaults: () => ({ unit: /^en-US/.test(navigator.language) ? "f" : "c" }),
  render(body, ctx) {
    const c = ctx.config;
    const setPlace = (name, lat, lon) => { Object.assign(c, { name, lat, lon }); ctx.save(); ctx.refresh(); };

    if (c.lat == null) {
      const input = h("input", { type: "text", placeholder: "City name", "aria-label": "City" });
      const msg = h("p", { class: "hint" });
      const search = async () => {
        if (!input.value.trim()) return;
        msg.textContent = "Searching…";
        try {
          const r = await getJson("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + encodeURIComponent(input.value.trim()), 24 * 3600e3);
          const p = r.results && r.results[0];
          if (!p) { msg.textContent = "No match. Try another city."; return; }
          setPlace([p.name, p.admin1, p.country_code].filter(Boolean).join(", "), p.latitude, p.longitude);
        } catch (e) { msg.textContent = "Search failed: " + e.message; }
      };
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") search(); });
      body.replaceChildren(
        h("div", { class: "row" }, input, h("button", { class: "btn", type: "button", onclick: search }, "Set")),
        h("button", { class: "btn", type: "button", onclick: () => {
          navigator.geolocation
            ? navigator.geolocation.getCurrentPosition(
                (p) => setPlace("My location", p.coords.latitude, p.coords.longitude),
                () => { msg.textContent = "Location blocked. Type a city instead."; })
            : (msg.textContent = "Geolocation not supported.");
        } }, "Use my location"),
        msg);
      return;
    }

    loading(body);
    const f = c.unit === "f";
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${c.lat}&longitude=${c.lon}` +
      `&current=temperature_2m,weather_code,wind_speed_10m&daily=weather_code,temperature_2m_max,temperature_2m_min` +
      `&timezone=auto&temperature_unit=${f ? "fahrenheit" : "celsius"}&wind_speed_unit=${f ? "mph" : "kmh"}`;
    getJson(url, 15 * 60e3).then((d) => {
      const cur = d.current, dl = d.daily;
      body.replaceChildren(
        h("div", { class: "muted" }, c.name),
        h("div", { class: "big" }, WMO_ICON(cur.weather_code), " ", Math.round(cur.temperature_2m), "°", f ? "F" : "C"),
        h("div", { class: "muted" }, WMO[cur.weather_code] || "", " · wind ", Math.round(cur.wind_speed_10m), f ? " mph" : " km/h"),
        h("div", { class: "forecast" }, dl.time.slice(0, 5).map((t, i) =>
          h("div", {},
            h("div", { class: "muted" }, new Date(t + "T12:00").toLocaleDateString([], { weekday: "short" })),
            h("div", {}, WMO_ICON(dl.weather_code[i])),
            h("div", {}, Math.round(dl.temperature_2m_max[i]), "°"),
            h("div", { class: "muted" }, Math.round(dl.temperature_2m_min[i]), "°")))),
        h("div", { class: "row" },
          h("button", { class: "btn small", type: "button", onclick: () => { c.unit = f ? "c" : "f"; ctx.save(); ctx.refresh(); } }, "°" + (f ? "C" : "F")),
          h("button", { class: "btn small", type: "button", onclick: () => { delete c.lat; delete c.lon; ctx.save(); ctx.refresh(); } }, "Change city")));
    }).catch((e) => failed(body, e));
  }
};

Widgets.hn = {
  name: "Hacker News", desc: "Top tech stories", defaults: () => ({}),
  render(body) {
    loading(body);
    getJson("https://hacker-news.firebaseio.com/v0/topstories.json", 5 * 60e3)
      .then((ids) => Promise.all(ids.slice(0, 10).map((id) => getJson(`https://hacker-news.firebaseio.com/v0/item/${id}.json`, 30 * 60e3))))
      .then((items) => body.replaceChildren(h("ul", { class: "list" }, items.filter(Boolean).map((it) =>
        h("li", {},
          link(it.title, it.url || `https://news.ycombinator.com/item?id=${it.id}`),
          h("div", { class: "hint" }, it.score, " points · ", link(`${it.descendants || 0} comments`, `https://news.ycombinator.com/item?id=${it.id}`))))))
      ).catch((e) => failed(body, e));
  }
};

Widgets.wiki = {
  name: "On this day", desc: "Historical events from Wikipedia", defaults: () => ({}),
  render(body) {
    loading(body);
    const d = new Date(), mm = String(d.getMonth() + 1).padStart(2, "0"), dd = String(d.getDate()).padStart(2, "0");
    getJson(`https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/${mm}/${dd}`, 12 * 3600e3).then((r) => {
      const events = r.events.slice().sort((a, b) => b.year - a.year).filter((_, i) => i % 3 === 0).slice(0, 6);
      body.replaceChildren(h("ul", { class: "list" }, events.map((e) =>
        h("li", {}, h("strong", {}, e.year, " "), e.pages && e.pages[0] && e.pages[0].content_urls
          ? link(e.text, e.pages[0].content_urls.desktop.page) : e.text))));
    }).catch((e) => failed(body, e));
  }
};

Widgets.apod = {
  name: "NASA picture of the day", desc: "Astronomy Picture of the Day", wide: true, defaults: () => ({}),
  render(body) {
    loading(body);
    getJson("https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY", 6 * 3600e3).then((d) => {
      const media = d.media_type === "image"
        ? h("img", { class: "media", src: safeUrl(d.url) || "", alt: d.title, loading: "lazy" })
        : h("p", {}, link("Watch today's video ↗", d.url));
      body.replaceChildren(media, h("h3", {}, d.title), h("p", { class: "muted" }, (d.explanation || "").slice(0, 280), "…"));
    }).catch((e) => failed(body, e));
  }
};

Widgets.trivia = {
  name: "Trivia", desc: "One question at a time (Open Trivia DB)", defaults: () => ({ score: 0, asked: 0 }),
  render(body, ctx) {
    const c = ctx.config;
    const next = async () => {
      loading(body);
      try {
        // Open Trivia DB rate-limits to one request per ~5s; encode=url3986 avoids HTML entities.
        const r = await (await fetch("https://opentdb.com/api.php?amount=1&encode=url3986")).json();
        if (!r.results || !r.results[0]) throw new Error("Slow down — try again in a few seconds.");
        const q = r.results[0], dec = decodeURIComponent;
        const answers = [...q.incorrect_answers, q.correct_answer].map(dec).sort(() => Math.random() - 0.5);
        const right = dec(q.correct_answer);
        const btns = answers.map((a) => h("button", { class: "btn", type: "button", onclick: (e) => {
          c.asked++; if (a === right) c.score++; ctx.save();
          btns.forEach((b) => { b.disabled = true; if (b.textContent === right) b.classList.add("right"); });
          if (a !== right) e.currentTarget.classList.add("wrong");
          score.textContent = `Score ${c.score}/${c.asked}`;
        } }, a));
        const score = h("span", { class: "hint" }, `Score ${c.score}/${c.asked}`);
        body.replaceChildren(
          h("div", { class: "hint" }, dec(q.category), " · ", q.difficulty),
          h("p", {}, dec(q.question)),
          h("div", { class: "answers" }, btns),
          h("div", { class: "row" }, h("button", { class: "btn small", type: "button", onclick: next }, "Next question"), score));
      } catch (e) {
        body.replaceChildren(h("p", { class: "err" }, e.message), h("button", { class: "btn small", type: "button", onclick: next }, "Retry"));
      }
    };
    next();
  }
};

Widgets.cocktail = {
  name: "Random cocktail", desc: "A new drink idea (TheCocktailDB)", defaults: () => ({}),
  render(body) {
    const go = () => {
      loading(body);
      fetch("https://www.thecocktaildb.com/api/json/v1/1/random.php").then((r) => r.json()).then((r) => {
        const d = r.drinks[0];
        const ings = [];
        for (let i = 1; i <= 15; i++) if (d["strIngredient" + i]) ings.push([d["strMeasure" + i] || "", d["strIngredient" + i]].join(" ").trim());
        body.replaceChildren(
          ...(safeUrl(d.strDrinkThumb) ? [h("img", { class: "media", src: safeUrl(d.strDrinkThumb), alt: d.strDrink, loading: "lazy" })] : []),
          h("h3", {}, d.strDrink),
          h("p", { class: "muted" }, ings.join(" · ")),
          h("p", {}, d.strInstructions),
          h("button", { class: "btn small", type: "button", onclick: go }, "Another"));
      }).catch((e) => failed(body, e));
    };
    go();
  }
};

Widgets.notes = {
  name: "Notes", desc: "A scratchpad that saves as you type", defaults: () => ({ text: "" }),
  render(body, ctx) {
    const ta = h("textarea", { placeholder: "Type anything…", "aria-label": "Notes" });
    ta.value = ctx.config.text;
    ta.addEventListener("input", () => { ctx.config.text = ta.value; ctx.save(); });
    body.replaceChildren(ta);
  }
};

Widgets.todo = {
  name: "To-do list", desc: "Simple checklist", defaults: () => ({ items: [] }),
  render(body, ctx) {
    const items = ctx.config.items;
    const input = h("input", { type: "text", placeholder: "Add a task", "aria-label": "New task" });
    const add = () => { const t = input.value.trim(); if (!t) return; items.push({ t, d: false }); ctx.save(); ctx.refresh(); };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") add(); });
    body.replaceChildren(
      h("ul", { class: "list todo" }, items.map((it, i) =>
        h("li", { class: it.d ? "done" : "" },
          h("input", { type: "checkbox", checked: it.d, "aria-label": it.t, onchange: () => { it.d = !it.d; ctx.save(); ctx.refresh(); } }),
          h("span", {}, it.t),
          h("button", { class: "btn small", type: "button", "aria-label": "Delete task", onclick: () => { items.splice(i, 1); ctx.save(); ctx.refresh(); } }, "✕")))),
      h("div", { class: "row" }, input, h("button", { class: "btn", type: "button", onclick: add }, "Add")));
  }
};

Widgets.links = {
  name: "Bookmarks", desc: "Your favourite sites",
  defaults: () => ({ items: [{ t: "Wikipedia", u: "https://wikipedia.org" }, { t: "YouTube", u: "https://youtube.com" }] }),
  render(body, ctx) {
    const items = ctx.config.items;
    const t = h("input", { type: "text", placeholder: "Name", "aria-label": "Bookmark name" });
    const u = h("input", { type: "url", placeholder: "https://…", "aria-label": "Bookmark URL" });
    const add = () => {
      let raw = u.value.trim();
      if (raw && !/^https?:\/\//i.test(raw)) raw = "https://" + raw;
      const url = safeUrl(raw);
      if (!url) return;
      items.push({ t: t.value.trim() || new URL(url).hostname, u: url }); ctx.save(); ctx.refresh();
    };
    body.replaceChildren(
      h("ul", { class: "list" }, items.map((it, i) =>
        h("li", { class: "row" }, link(it.t, it.u),
          h("button", { class: "btn small", type: "button", "aria-label": "Remove bookmark", style: "margin-left:auto", onclick: () => { items.splice(i, 1); ctx.save(); ctx.refresh(); } }, "✕")))),
      h("div", { class: "row" }, t, u, h("button", { class: "btn", type: "button", onclick: add }, "Add")));
  }
};
