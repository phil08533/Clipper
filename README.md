# My Start Page

A customizable homepage (PWA) where each user adds, removes, resizes and rearranges their own widgets.
No build step, no API keys, no backend — just static files.

## Run it
```
python3 -m http.server 8000   # then open http://localhost:8000
```
Deploy the folder to any static host (GitHub Pages, Netlify, Cloudflare Pages). Service workers and
"Install app" need HTTPS (localhost is fine for testing).

## Widgets
Clock, Weather (Open-Meteo), Hacker News, Wikipedia "On this day", NASA picture of the day, Trivia
(Open Trivia DB), Random cocktail (TheCocktailDB), Notes, To-do, Bookmarks.

Layouts live in `localStorage`; Settings → *Copy layout* / *Load layout* moves or shares one.

## Add a widget
In `widgets.js`, add an entry to `Widgets`:
```js
Widgets.myWidget = {
  name: "My widget", desc: "Shown in the catalog", defaults: () => ({}),
  render(body, ctx) { body.textContent = "hello"; /* ctx.config, ctx.save(), ctx.refresh() */ }
};
```
Build DOM with `h()` / `textContent`, never `innerHTML`, so third-party API text can't inject markup.

## Making money
Paste your ad network's snippet inside `<aside id="ad-slot">` in `index.html`. Revenue depends on traffic,
so plan how people will find the site. Before monetizing, check each API's terms: some (TheMealDB,
Reddit, Jikan) restrict commercial use, Wikipedia text requires CC BY-SA attribution, and NASA's
`DEMO_KEY` is heavily rate-limited — get a free key at api.nasa.gov for production.
