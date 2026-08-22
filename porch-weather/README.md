# Porch Weather

An hour-by-hour red / yellow / green rating for whether it's a nice time to sit
on the porch, based on your local forecast.

Open `index.html` in a browser. That's the whole thing — one file, no build step,
no server, no API key, no account. Forecast data comes from
[Open-Meteo](https://open-meteo.com/), which is free for personal use.

## What it rates

Each hour gets a rating for five factors, plus one overall verdict:

| Factor | Green | Yellow | Red |
| --- | --- | --- | --- |
| Temperature (feels-like) | 64–78 °F | ~55–64 / 78–86 °F | below ~50 or above ~90 °F |
| Humidity (scored on dew point) | dew point under 60 °F | 60–68 °F | above ~70 °F — muggy |
| Wind | 0–10 mph, gusts under 18 | 10–18 mph, or gusty | over ~20 mph, or gusts over 30 |
| Rain | under 15% chance | 15–50% | over ~55%, or rain actually falling |
| Cloud cover | depends on your sun preference | | |

Humidity is scored on **dew point** rather than relative humidity, because that's
what actually feels sticky — 80% humidity at 55 °F is a crisp morning, 80% at
78 °F is a swamp. The relative-humidity number is still what's displayed.

The overall hour rating is a weighted blend (temp 30%, humidity 20%, wind 20%,
rain 20%, cloud 10%) with two overrides:

- An hour is green only when **every** factor is green. One yellow factor keeps
  the hour at yellow.
- One genuinely bad factor — thunderstorms, 25 mph wind, 95 °F — makes the whole
  hour red regardless of how good everything else looks.

After dark, cloud cover stops counting toward the score.

## Using it

- **Location** — search by city or ZIP, or hit "Use my location". It's remembered
  in the browser afterward. You can also link straight to a spot:
  `index.html?lat=35.60&lon=-82.55&name=Home`
- **Right now** — the current hour's verdict, plus the best remaining stretch today.
- **By hour** — seven days of forecast, as tabs. The color strip is all 24 hours at
  a glance (past hours dimmed, current hour outlined); click a block to jump to
  that row.
- **Week** — all seven days as one grid: a row per day, a column per hour, with the
  count of green hours beside each day and a "best bet this week" callout. Tap any
  block to drop into that day's hour-by-hour detail.
- **Settings** — sun preference (some people want sun on the porch, some want
  shade), whether you run hot or cold, °F/°C, and whether to show the overnight
  hours.

Settings and location live in `localStorage` — nothing is sent anywhere except
the forecast request itself.

## Hosting it

It's a static file, so anything that serves files works: open it from disk, drop
it in Dropbox/iCloud, or publish this folder with GitHub Pages and bookmark it on
your phone. Browser geolocation needs `https://` (or `file://`) — over plain
`http://` from another machine, use the search box or the `?lat=&lon=` link form.
