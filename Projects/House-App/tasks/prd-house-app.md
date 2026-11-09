# PRD: House App

Status: Draft v2 · Updated 2026-11-09 after LLM Council round 2 · Owner: Vihang

## 1. Introduction / Overview

We are two adults who moved into a house in northeast Calgary in fall 2026. Right now, knowledge about the house is in one person's head or in a pile of paper: model numbers, filter sizes, where the water shutoff is, warranty dates, contractors. Recurring maintenance is easy to forget. The thermostat is a Honeywell Home (Resideo) unit with its own app. The lights are not yet known to be smart.

**House App** gives us one place, on both iPhones and in a browser on our laptops, to do four things:

1. Look up anything about the house.
2. Get pushed reminders for recurring tasks, each assigned to one of us.
3. Keep a dated log of what was done. The log doubles as evidence for warranty and insurance claims.
4. See and change the temperature (and the lights, if they become smart).

**Architecture in one sentence:** Home Assistant (HA) runs on a small mini PC at home and handles devices, user accounts, push notifications and backups. Our custom code is a single **HA add-on** that appears as a page inside the HA Companion app. We reach it from anywhere over Tailscale. Nothing is exposed to the public internet.

**Home Assistant, briefly.** HA is free, open-source software that runs on a computer in the house. It connects to more than 2,000 smart-home brands (thermostats, lights, sensors) and controls them from one app. **HA OS** is the all-in-one install of HA, built for a dedicated machine. An **add-on** is a Docker container that HA runs, shows in its sidebar, and includes in its backups.

**Goal:** neither of us misses a recurring house task or a warranty deadline. Either of us can find any house fact from a phone in under 30 seconds.

## 2. Goals

1. Phase 0 is finished before any hardware is bought: warranty status confirmed, inherited accounts reset, house inventory captured.
2. Both of us get a push notification on our own iPhone when a task assigned to us is due, without opening anything first.
3. Any house fact can be found from a phone in 30 seconds or less.
4. Freeze protection: if indoor temperature drops below 15 °C, or the thermostat goes offline for 30 minutes or more, both phones are alerted. A second alert path from the Honeywell app does not depend on our hardware at all.
5. Zero ports open on the home router. Running cost is electricity only, under $5 CAD/month, unless we choose the paid Nabu Casa fallback.
6. The house works normally when our box is down: the thermostat, the Honeywell app and the wall switches all keep working.
7. Data is backed up nightly with at least one copy outside the house, and can be exported as JSON + Markdown at any time.

## 3. User Stories

- As either of us, I want a push notification when a task assigned to me is due, so I don't have to remember to check.
- As my wife, I want everything in one app on my iPhone (the HA Companion app), so I don't have to learn several tools.
- As either of us, I want to search "furnace filter" and see the size, the location, the date it was last changed and where to buy one.
- As either of us, I want each recurring task to include full steps, parts and photos, so whoever does it doesn't have to ask.
- As the person who did a task, I want to mark it done and add a note or photo, so we have a dated history.
- As homeowners, we want a dated maintenance log, so we can show the builder or insurer that maintenance was done.
- As homeowners, we want to log a defect (photo, room, date), so we can claim it before warranty coverage ends.
- As either of us, while away, I want an alert if the furnace stops or the house gets cold, so the pipes don't freeze.
- As either of us, I want to change the temperature from anywhere.
- As Vihang, on my Windows laptop, I want the same app in a browser.

## 4. Functional Requirements

### 4.0 Phase 0: no code, no purchase (do this week)

1. **Warranty (confirmed).** We are the first owners. We took possession on **2026-10-20**, and the builder's check-in walkthrough was the same day. Alberta new home warranty coverage therefore ends on:
   - **2027-10-20**: 1 year, materials and labour
   - **2028-10-20**: 2 years, delivery and distribution systems
   - **2031-10-20**: 5 years, building envelope
   - **2036-10-20**: 10 years, structure

   Deficiencies reported at check-in are booked for repair on **2026-11-24**. After that visit, inspect each repair and record which items are fixed and which are still open. Report anything still open to the builder in writing. Keep a running defect list and submit it **before 2027-10-20**. Do one full house walk-through in August/September 2027 before submitting.
2. Pull the thermostat faceplate and record the exact model number. Note any HomeKit or Matter setup code.
3. Photograph the light switches and some bulbs. Record whether any are smart, and whether the switch boxes have neutral wires.
4. Reset or transfer inherited access: the thermostat's Resideo account, garage door openers, smart locks or keypads, and Wi-Fi.
5. Turn on the low-temperature alert in the Honeywell/Resideo app for both phones.
6. Walk the house with a phone camera. Fill a spreadsheet with every appliance and system (name, location, brand, model, serial, filter or consumable size) and key locations (water shutoff, gas shutoff, electrical panel and breaker map). Keep this file **outside the git repo**.
7. Take dated photos of the roof, siding and windows as a record before any hail claim.
8. Create a shared Apple Reminders list called "House" and use it for 2 weeks. Write down what it couldn't do. That list feeds Phase 2's scope.

### 4.1 Phase 1: platform setup (buy hardware, still no custom code)

9. Install **HA OS** on an Intel N100-class mini PC with 16 GB RAM and a 512 GB SSD.
10. Create a separate HA user (non-admin) for each of us.
11. Install the **Tailscale add-on** in HA. Install Tailscale on both iPhones and both laptops. Set the iPhones' Tailscale VPN to stay always on ("VPN On Demand") so it never needs switching on by hand.
12. Install the HA Companion app on both iPhones and sign each person in as their own HA user. Turn off location tracking unless both of us agree to it.
13. Add the Honeywell thermostat integration. Which one depends on the model found in requirement 2:
    - Matter or HomeKit, if supported (local control, preferred)
    - otherwise Honeywell Lyric or Total Connect Comfort (Resideo cloud)
    If pairing would remove the thermostat from Apple Home or the Honeywell app, document what changes before doing it.
14. Build the freeze-alert automation in HA's UI: notify both phones when indoor temperature drops below 15 °C, or when the thermostat has been unavailable for 30 minutes or more.
15. Configure HA's built-in nightly backups with one copy outside the house (cloud storage, or a laptop that isn't kept at home), and keep 14 days. Test a restore once.
16. **Phase 1 is done when my wife changes the temperature from her phone while away from home, without help.** If she won't, stop and fix the experience before writing any code.

### 4.2 Phase 2: the "House" add-on (custom code)

**Knowledge base**

17. Store **items**. Each item has a name, a category (Appliance, System, Room, Utility, Contact, Document, Note), a location in the house, a Markdown body and tags.
18. Appliance and System items also have these optional fields: brand, model, serial, install date, warranty end date, consumable part and where to buy it.
19. Allow photos and PDFs to be attached to any item.
20. Provide full-text search across items, tasks and log entries, using SQLite FTS5.
21. Import the Phase 0 spreadsheet (CSV) into items.

**Tasks and reminders**

22. A task has:
    - a title
    - a Markdown description
    - an assignee: one of the two HA users, or Either
    - a due date and time
    - an optional recurrence
    - an optional linked item
    - a priority
23. Recurrence comes in two kinds:
    - **after completion**, for example "90 days after last done"
    - **calendar**, for example "every October 1", stored as an RFC 5545 RRULE and evaluated with `python-dateutil`
24. When a task is due, send a push to the assignee's phone through HA's `notify.mobile_app_<device>` service. A task assigned to "Either" goes to both phones.
25. Send at 09:00 `America/Edmonton` on the due date. If the task is still open, send again daily at 09:00. Store `last_notified_at` so a restart never sends the same reminder twice.
26. Allow marking a task done or snoozing it (1 day or 1 week).
27. Provide a quick-add field (title + date).
28. Show overdue tasks first on the home view.

**Maintenance and defect log**

29. Completing a task creates a log entry: who, when, a note, optional photos and an optional cost.
30. Allow manual log entries with a type: Maintenance, Repair or **Defect**. Defect entries also record the room, a photo and the relevant warranty coverage period.
31. Export the defect list as a dated Markdown/PDF report to send to the builder.
32. Show the log history for each item, newest first.

**Seed content and export**

33. Offer an optional starter list of Calgary tasks that the user accepts or rejects one at a time:
    - furnace filter
    - humidifier pad (fall)
    - HRV filter, if the house has an HRV
    - smoke/CO detector test
    - sprinkler blowout before the first freeze
    - outdoor tap shutoff before the first freeze
    - gutters (spring and fall)
    - sump pump and window wells before the spring melt
    - water heater flush
    - dryer vent cleaning
    - roof and siding check after hail
    - each warranty end date from requirement 1, with reminders 60 and 14 days before it (seeded, not optional)
    - a one-off task: "Inspect the 2026-11-24 deficiency repairs and log any open items"
34. Provide a one-click export of all data as JSON plus a folder of Markdown files.

### 4.3 Phase 3: one ML feature (pick one once Phase 2 has been in use for a month)

35. **Option A, manuals Q&A:** ask a question in plain language and get an answer drawn from the attached manuals and warranty PDFs, with the source page cited.
36. **Option B, thermostat runtime analytics:** compare heating runtime against outdoor temperature (Environment Canada data), and flag unusual rises such as a clogged filter or a failing furnace. This is only possible if the thermostat integration exposes runtime history.

## 5. Non-Goals (Out of Scope)

- No native iOS app and no separate PWA. The add-on page inside the HA Companion app is the mobile app.
- No custom device drivers and no direct vendor API calls. Devices go through HA only.
- No custom device-control page. HA's own dashboard already does this.
- No exposure to the public internet and no router port forwarding.
- No GPU hardware, Jetson, cameras or Frigate.
- No Kubernetes and no cloud hosting.
- No multi-household features, sign-up flow, or "seed packs for other homeowners" product.
- No storing of alarm codes, door codes or passwords.
- Nothing in this project replaces the thermostat, the Honeywell app or the wall switches.

## 6. Design Considerations

- The add-on shows as a sidebar panel ("House") in HA and the Companion app, using HA **ingress**. Ingress means HA serves the add-on's web page itself, so no extra port or login is needed.
- **Mobile-first.** Tabs: Today (overdue, due today, this week) · Tasks · House (items) · Log.
- Completing a task takes one tap. Adding a note or photo is an optional second step.
- Quick add must take under 15 seconds. Test it on my wife's phone with no instructions.
- Light and dark themes follow HA's theme where possible.
- Task and item descriptions render as Markdown, with images inline.

## 7. Technical Considerations

### 7.1 Architecture

```
iPhone (HA Companion app) / laptop browser
        │  Tailscale (always-on VPN)
        ▼
N100 mini PC ── HA OS
   ├─ Home Assistant Core ── Honeywell integration (Matter/HomeKit local, or Resideo cloud)
   │        ├─ users (one per person), Companion push, freeze-alert automation
   │        └─ nightly backups ─▶ offsite copy
   ├─ Tailscale add-on
   └─ "House" add-on (FastAPI + SQLite in /data)
            ├─ served through HA ingress (sidebar panel, HA login)
            └─ calls http://supervisor/core/api (SUPERVISOR_TOKEN) for notify + states
```

### 7.2 Hardware

- An Intel N100/N150 mini PC with 16 GB RAM and a 512 GB SSD, about $200–250 CAD. This is the same price as a full Raspberry Pi 5 kit, with double the RAM and a normal SSD.
- Use wired Ethernet to the router.
- A GPU is not needed. If the Phase 3 manuals Q&A needs a language model, call a hosted API. Don't buy GPU hardware for it.
- The 2 TB drive is optional. If bought, it is a second local backup copy only. It never replaces the offsite copy.
- A small UPS (battery backup) is optional.

### 7.3 House add-on

- **Stack:** Python 3.12, FastAPI, SQLite (WAL mode, FTS5), `python-dateutil` and `zoneinfo`. Frontend: Vite + vanilla JS, matching [Portfolio](../../Portfolio).
- **Packaging:** a local HA add-on with `config.yaml` (`ingress: true`, `homeassistant_api: true`, `panel_icon`, `panel_title: House`) and a `Dockerfile`. During development, install it from the HA `/addons` folder.
- **Ingress paths:** HA serves the add-on under a path prefix. All frontend URLs must be relative (Vite `base: './'`), and FastAPI must handle the `X-Ingress-Path` header.
- **Identity:** read the HA user from the ingress headers (`X-Remote-User-Id`, `X-Remote-User-Name`). The app has no login of its own.
- **HA API access:** call `http://supervisor/core/api/...` using the `SUPERVISOR_TOKEN` environment variable. **Do not create a long-lived access token.**
- **Data:** the SQLite database and attachments live in the add-on's `/data` folder, so HA backups include them automatically.
- **Scheduler:** one background loop that runs every minute. It is idempotent: `last_notified_at` prevents duplicate sends.
- **Migrations:** forward-only, numbered SQL files, the same pattern as Jobs-Web-App.
- **Tests:** pytest for next-due-date calculation (DST changes, month-end dates, after-completion recurrence) and for the no-duplicate-notification rule.

### 7.4 Remote access

- **Default:** Tailscale (free personal plan). Both people sign in and share one tailnet. Zero open ports.
- **Fallback, if the VPN causes friction for my wife:** Nabu Casa (HA Cloud, about $65 USD/year). It gives remote access with no VPN on the phone and also supports HA. Decide after 2 weeks of Phase 1.

### 7.5 Repository and privacy

- The add-on code lives in `Projects/House-App` in the **public** VShah- monorepo. House data never enters git: the Phase 0 spreadsheet, the database, photos, model and serial numbers, and the address.
- `.gitignore` from the first commit: `*.db`, `*.csv`, `data/`, `backups/`, `.env`.
- Seed content is generic Calgary maintenance only.

## 8. Success Metrics

- Phase 0 is finished within 2 weeks. The 2026-11-24 repairs are inspected and logged. The 1-year defect list is submitted before 2027-10-20.
- Phase 1 gate: my wife changes the temperature remotely without help.
- After 60 days of Phase 2: both of us have completed at least one task that started from a push notification, and at least 90% of recurring tasks are done within 3 days of their due date.
- My wife opens the House panel at least weekly without being asked (checked at 30 and 90 days).
- Zero missed warranty deadlines, and zero freeze incidents.
- A restore from backup has been tested once. An external port scan shows zero open ports.

## 9. Open Questions

1. ~~Possession date~~: resolved. It was 2026-10-20, we are the first owners, and all coverage periods are running (see requirement 1).
2. What is the exact thermostat model? Does it support Matter or HomeKit?
3. Are any of the lights smart? Do the switch boxes have neutral wires? If we buy smart lights, they must be Matter-certified.
4. What OS is my wife's computer (Mac or Windows; personal or work)? A work laptop may block Tailscale. Browser access to HA works on either OS.
5. Where does the offsite backup go: Google Drive, OneDrive, Backblaze B2, or a laptop kept elsewhere?
6. Phase 3: manuals Q&A or thermostat analytics? Decide after a month of Phase 2.
7. Does the house have an HRV and a whole-home humidifier? This decides which seed tasks apply.
