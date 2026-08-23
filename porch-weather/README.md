# Boyle Porch Weather

An hour-by-hour red / yellow / green rating for whether it's a nice time to sit
on the porch, based on local conditions at any of the Boyle porches.

## The porches

Four saved locations sit as one-tap buttons on the location card:

| Porch | Coordinates |
| --- | --- |
| Essex, Connecticut | 41.3548, -72.3915 |
| Alexandria, Virginia | 38.8048, -77.0469 |
| Ketchum, Idaho | 43.6805, -114.3637 |
| Hopkinton, New Hampshire | 43.1917, -71.6803 |
| Lucy | see below |

"Lucy" is not a place. Tapping it replaces the entire forecast with **Go outside!**
in very large type, on the grounds that Lucy was unimpressed with this application
and observed that you can simply go outside and see what the weather looks like.
A button underneath brings the forecast back, and the mode is deliberately not
remembered — reload and you have a weather dashboard again.

A first visit opens on Essex; after that it remembers whichever porch you last
looked at. "Somewhere else" still opens the search box and the use-my-location
button for anywhere that isn't on the list. To change the saved set, edit the
`PRESETS` array near the top of the script in `index.html` — each entry is a
short button label, a full name, and a latitude/longitude.

Open `index.html` in a browser. That's the whole thing — one file, no build step,
no server, no API key, no account. Forecast data comes from
[Open-Meteo](https://open-meteo.com/), which is free for personal use.

## The scale

Every hour gets a **score out of 100** — shown on its pill and beside the verdict —
and the score picks one of five tiers:

| Tier | Score | Means |
| --- | --- | --- |
| ★ Glorious | 88–100 | drop what you're doing |
| ✓ Good | 74–87 | genuinely nice out |
| ~ OK | 58–73 | perfectly sittable, nothing special |
| ! Meh | 42–57 | you'd manage, but you wouldn't linger |
| ✕ Nope | under 42 | stay in |

The number is where the nuance lives: a 73 and a 59 are both "OK", but only one of
them is nearly good. Each tier carries its own glyph and word as well as its colour,
so nothing depends on telling two greens apart.

## What it rates

Each hour is scored on six factors, which combine into that overall number:

| Factor | Scores well | Middling | Scores badly |
| --- | --- | --- | --- |
| Temperature (feels-like) | 62–80 °F | ~53–62 / 80–86 °F | below ~48 or above ~92 °F |
| Humidity (scored on dew point) | dew point under 63 °F | 63–70 °F | above ~72 °F — muggy |
| Wind | 0–10 mph, gusts under 18 | 10–18 mph, or gusty | over ~20 mph, or gusts over 30 |
| Rain | under 15% chance | 15–50% | over ~55%, or rain actually falling |
| Cloud cover | depends on your sun preference | | |
| Air quality (US AQI) | under ~75 | 75–135 | above ~135 — smoke or smog |

Every hour shows both temperatures: the feels-like reading, which the rating is
built on, and the actual air temperature next to it. They part company whenever
wind chill or humidity is doing something to the air.

Humidity is scored on **dew point** rather than relative humidity, because that's
what actually feels sticky — 80% humidity at 55 °F is a crisp morning, 80% at
78 °F is a swamp. The relative-humidity number is still what's displayed.

Air quality comes from Open-Meteo's air-quality service as the US AQI, fetched
alongside the forecast. It's the factor that catches the 74°-and-sunny afternoon
that's actually full of wildfire smoke. If that request fails the chip reads "—"
and the hour is scored on the other five factors, so a bad air-quality response
never costs you the forecast.

The hour's score is a weighted blend (temp 30%, humidity 20%, wind 20%, rain 20%,
air 12%, cloud 10%), and then one rule applies: **an hour can score no more than 18
points above its worst factor.**

That single rule replaces what used to be three hard cliffs, and it's what keeps a
lovely afternoon from being demoted over one imperfect number. A thunderstorm
scores about 5, so the hour lands at 23 — Nope — no matter how pleasant the
temperature is. An afternoon that's merely a bit muggy scores 65 on humidity, so
the hour can still reach 83 and read Good.

After dark, cloud cover stops counting toward the score.

## Icons

Every hour shows what the sky is doing — sun, moon, partly cloudy, overcast, fog,
drizzle, rain, snow, thunderstorm — mapped from the forecast's WMO weather code,
with day and night variants. The five factor chips carry their own icons
(thermometer, droplet for humidity, wind, rain, cloud), colored by that factor's
rating and paired with a ✓ / ~ / ✕ mark so the meaning never rests on color alone.

In the week grid, a block picks up a small marker when there's rain, snow or a
thunderstorm coming, or when wind or humidity is the specific thing spoiling that
hour. Merely cloudy hours are left unmarked there — in an overcast week that
marker would end up on every block and stop meaning anything.

## The masthead

The header carries a sky wash, a hill silhouette and a sun or moon that follow the
current hour: daylight blue, a warm band in the hour either side of sunrise and
sunset, and a deep blue night with the moon and a few stars. It's decoration, but
it's honest decoration — it always matches the hour the dashboard is showing.

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
