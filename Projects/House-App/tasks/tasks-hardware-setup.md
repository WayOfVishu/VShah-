# Tasks: Hardware and platform setup (home office)

Source: [prd-house-app.md](prd-house-app.md) (§4.1 Phase 1, §7.2, §7.4)

## Relevant Files

- `Projects/House-App/docs/runbook.md` - The one-page "if this breaks" guide for the household. Generic content only: no IP addresses, keys or address.
- `Projects/House-App/README.md` - Project overview. Links to the runbook and the PRD.

### Notes

- Almost everything here is done in a browser or on the hardware itself, not in code. Only task 8.0 produces committed files.
- Never write IP addresses, Tailscale names, tokens, backup encryption keys or the house address into the repo. The repo is public.
- Settle open question 2 (thermostat model) before 5.0. Phase 0 item 2 in the PRD covers this.

### Networking: the office has no Ethernet jack

The builder didn't wire the office for Ethernet, so the mini PC needs another way to reach the router. Home Assistant uses very little bandwidth. What matters is **reliability**: the box should never drop off the network in the middle of the night. These are the options, best first.

**1. MoCA (Multimedia over Coax Alliance).**
- **What it is:** MoCA sends a normal Ethernet connection over the round TV coax cables already inside the walls. You buy two adapters:
  - one plugs into a coax outlet near the router, plus an Ethernet cable to the router
  - one plugs into a coax outlet in the office, plus an Ethernet cable to the mini PC

  The two adapters talk to each other over the coax. To the mini PC, it looks exactly like a wired connection: near-Ethernet speed and very stable.
- **What you need:** a coax outlet in the office, and a coax outlet near the router (or the router moved near one). In a new build, the coax runs usually meet at a structured-media panel, often in the basement or utility room. The office line and the router's line have to be connected there (through a splitter rated 5–1675 MHz, or directly with a coupler).
- **Cost:** about $150–200 CAD for a pair of **MoCA 2.5** adapters.
- **If your internet comes over coax** (cable internet, such as Rogers/Shaw), MoCA still works. Put a **MoCA PoE filter** (about $10) where the cable enters the house, so the signal stays inside your home. If your internet is fibre (common in new northeast Calgary builds, such as Telus PureFibre), the coax is probably unused and there's no conflict.
- **Check first:** look for a coax outlet (screw-on TV connector) in the office, and find the structured-media panel.

**2. A mesh Wi-Fi node with an Ethernet port, placed in the office.**
- **What it is:** a mesh system (for example eero, TP-Link Deco or Google Nest Wifi) has several units that link wirelessly. Most units have an Ethernet port on the back. Put one unit in the office and plug the mini PC into it. The box itself is wired; only the node-to-router hop is wireless.
- **Good fit if:** the house Wi-Fi already needs mesh coverage anyway.
- **Cost:** $0 if you already own a mesh system, otherwise about $150–300 CAD for a 2–3 pack.

**3. Powerline adapters.**
- **What it is:** two adapters that send network data over the house's electrical wiring, one at the router and one in the office, each plugged into a wall outlet.
- **Caveats:** speed and stability vary with the wiring and with which circuits the outlets are on. Plug them straight into the wall, never into a power bar or surge protector.
- **Cost:** about $80–120 CAD.

**4. Plain Wi-Fi on the mini PC.**
- **What it is:** use the mini PC's built-in Wi-Fi. HA OS supports this (Settings → System → Network). Home Assistant's traffic is small, so speed is fine.
- **Risk:** Wi-Fi drops and slow reconnects. Acceptable as a starting point if the office has strong signal. Run the initial install with a temporary Ethernet cable next to the router, then switch to Wi-Fi.
- **Cost:** $0.

**5. Don't host it in the office at all.**
- Put the mini PC next to the router (a shelf or the utility room) with a short Ethernet cable. It's free and the most reliable option. It's only worth skipping if the office location really matters to you (noise, access, keeping hardware together).

**Decision rule:**
- If the office has a coax outlet, use **MoCA**.
- Otherwise, if you have or want mesh, use **a mesh node**.
- Otherwise, start on **Wi-Fi** and upgrade only if HA shows dropouts.

You can check for dropouts after a week: if HA's history for the thermostat shows `unavailable` gaps that weren't caused by the thermostat itself, the network is dropping.

## Instructions for Completing Tasks

**IMPORTANT:** As you complete each task, you must check it off in this markdown file by changing `- [ ]` to `- [x]`. This helps track progress and ensures you don't skip any steps.

Example:
- `- [ ] 1.1 Read file` → `- [x] 1.1 Read file` (after completing)

Update the file after completing each sub-task, not just after completing an entire parent task.

## Tasks

- [ ] 0.0 Create feature branch
  - [ ] 0.1 From `main`, create and check out `Project/House-App` (this follows the repo's `Project/<Name>` convention)
- [ ] 1.0 Prepare the office spot and buy hardware
  - [ ] 1.1 Find where the router (or ISP modem) is and which room is the office
  - [x] 1.2 Check whether the office has a working Ethernet wall jack. Result: **none, the builder missed it.** See "Networking: the office has no Ethernet jack" above.
  - [ ] 1.3 Check for a coax (TV) outlet in the office and one near the router. Find the structured-media panel and note whether the internet service is fibre or cable.
  - [ ] 1.4 Pick the connection using the decision rule above (MoCA, then a mesh node, then Wi-Fi; or host next to the router) and buy any adapters needed
  - [ ] 1.5 If using MoCA: connect the office and router coax lines at the panel, install both adapters, and add a PoE filter if the internet comes over cable. Confirm a laptop gets a connection through the office adapter.
  - [ ] 1.6 Buy an Intel N100/N150 mini PC: 16 GB RAM, 512 GB NVMe SSD, at least one Ethernet port and built-in Wi-Fi (in case Wi-Fi is the fallback). Budget about $200–250 CAD.
  - [ ] 1.7 Buy or reuse an 8 GB+ USB stick (for the installer) and two short Ethernet cables (one for the adapter or node, one for the first install next to the router)
  - [ ] 1.8 Optional: a small UPS (battery backup) for the mini PC and the router. With MoCA, the office adapter needs to be on it too.
  - [ ] 1.9 Choose a spot with airflow (not on carpet, not in a closed drawer) near an outlet. Label the box "Home server: do not unplug".
- [ ] 2.0 Install HA OS
  - [ ] 2.1 Enter the BIOS (usually Del or F7 at power-on). Turn on UEFI boot and turn off Secure Boot. Set "Restore on AC power loss" to **Power On**.
  - [ ] 2.2 On the Windows laptop, write an Ubuntu live image to the USB stick (Rufus or balenaEtcher)
  - [ ] 2.3 Boot the mini PC from the USB stick. Download the `haos_generic-x86-64` image from home-assistant.io. Write it to the internal SSD with the Ubuntu "Disks" app ("Restore Disk Image"), following the official generic x86-64 guide.
  - [ ] 2.4 Shut down and remove the USB stick. For the first boot, connect Ethernet next to the router (temporarily, if the box will live in the office), then power on.
  - [ ] 2.5 From the laptop, open `http://homeassistant.local:8123` (or the device's IP from the router's client list). Wait for setup to finish.
  - [ ] 2.6 Onboarding: create your own owner (admin) account. Set the location to Calgary, the time zone to `America/Edmonton`, and metric units.
  - [ ] 2.7 Move the box to its final spot on the connection chosen in 1.4. If it's Wi-Fi, configure it first under Settings → System → Network while still wired, then unplug.
  - [ ] 2.8 In the router admin page, add a DHCP reservation (fixed IP) for the mini PC on its **final** interface. Wi-Fi and Ethernet have different MAC addresses, so the reservation has to match the one it actually uses.
  - [ ] 2.9 Settings → People → add your wife as a user (non-admin) with her own login
  - [ ] 2.10 Settings → System → Updates: install all pending HA OS and Core updates
  - [ ] 2.11 Install the official add-ons **Samba share** and **Terminal & SSH**, set strong passwords, and leave both reachable from the LAN/tailnet only. The add-on task list needs these.
  - [ ] 2.12 Turn on Advanced Mode in your user profile. This shows user IDs, which the add-on needs later.
- [ ] 3.0 Set up remote access with Tailscale
  - [ ] 3.1 Create a Tailscale account (personal plan, free). Invite your wife's Apple ID or Google account to the tailnet.
  - [ ] 3.2 In HA: Settings → Add-ons → Add-on Store, install **Tailscale**, start it, and open the web UI to sign the box into the tailnet
  - [ ] 3.3 In the Tailscale admin console, turn off key expiry for the HA machine and turn on MagicDNS
  - [ ] 3.4 Install Tailscale on both iPhones, sign in, and turn on **VPN On Demand** so it stays connected
  - [ ] 3.5 Install Tailscale on both laptops and sign in
  - [ ] 3.6 Test it: turn off Wi-Fi on a phone, then open `http://<ha-machine-name>:8123` over cellular
  - [ ] 3.7 Confirm the router has **no** port forwards. Run an external port scan (for example the ShieldsUP common ports test) and confirm everything is closed.
- [ ] 4.0 Set up the clients (phones and laptops)
  - [ ] 4.1 Install the **Home Assistant** Companion app on both iPhones
  - [ ] 4.2 In each app, set the internal URL (the LAN IP, used when on home Wi-Fi) and the external URL (the Tailscale MagicDNS name)
  - [ ] 4.3 Each person signs in as their own HA user and allows notifications
  - [ ] 4.4 In the Companion app, go to Settings → Sensors and turn off location sensors on both phones (unless you both agree to keep them)
  - [ ] 4.5 In HA, go to Developer Tools → Actions and send `notify.mobile_app_<phone>` to each phone. Write both service names down **outside the repo**; the add-on needs them.
  - [ ] 4.6 Bookmark the HA URL in the browser on both laptops. Check whether your wife's computer is a work machine that blocks Tailscale (PRD open question 4).
- [ ] 5.0 Connect the thermostat
  - [ ] 5.1 Pull off the faceplate and photograph the model number and any HomeKit or Matter setup code (skip if Phase 0 already did this)
  - [ ] 5.2 Look up which connection methods the model supports: Matter, HomeKit, or Resideo cloud only
  - [ ] 5.3 Connect it using the first option that applies:
    - **If Matter:** add it through Settings → Devices → Add Matter device, using the Companion app on an iPhone. Use Matter multi-admin so the Honeywell app keeps working.
    - **If HomeKit only:** add it with the HomeKit Device integration. Note that this removes it from Apple Home; that's acceptable, because Apple Home isn't part of the plan.
    - **If cloud only:** register an app at developer.honeywellhome.com. Add the consumer key and secret under HA Settings → Application Credentials, then add the **Honeywell Lyric** integration. Use **Total Connect Comfort** instead if it's an older TCC unit.
  - [ ] 5.4 Check the thermostat entity: the current temperature is shown, and a setpoint or mode change in HA also shows up in the Honeywell app
  - [ ] 5.5 Check that the Honeywell app still works on both phones
  - [ ] 5.6 Add a thermostat card to the default dashboard so it's the first thing your wife sees
- [ ] 6.0 Set up freeze protection
  - [ ] 6.1 In the Honeywell app, turn on the low-temperature alert (15 °C) for both phones. This is the backup alert that doesn't depend on the mini PC.
  - [ ] 6.2 Create an HA automation (in the UI): when the thermostat's current temperature stays below 15 °C for 10 minutes, notify both phones as an iOS critical alert (`push: {sound: {name: default, critical: 1, volume: 1.0}}`)
  - [ ] 6.3 Create a second automation: when the thermostat entity has been `unavailable` for 30 minutes, notify both phones
  - [ ] 6.4 Test both: temporarily raise the threshold above the current temperature, confirm both phones get the alert, then put it back
- [ ] 7.0 Set up backups
  - [ ] 7.1 Choose the offsite target (PRD open question 5): a cloud backup location in HA's backup settings (for example Google Drive or OneDrive), or a network share on a laptop that isn't kept at home
  - [ ] 7.2 Settings → System → Backups: automatic daily backups, keep 14, include add-ons, send to the offsite location
  - [ ] 7.3 Save the backup **encryption key** in a password manager that both of you can reach. Without it, the backups are useless.
  - [ ] 7.4 Download one backup to the laptop by hand
  - [ ] 7.5 Restore test: install HA OS in a Hyper-V or VirtualBox VM on the laptop, restore the backup, and confirm the users, automations and thermostat setup are all there. Delete the VM afterwards.
- [ ] 8.0 Gate and handover
  - [ ] 8.1 Gate test: your wife, away from home on cellular, changes the setpoint in the Companion app with no help. Note anything she struggles with.
  - [ ] 8.2 Fix that friction. If the VPN itself is the problem after 2 weeks, decide on the Nabu Casa fallback (PRD §7.4).
  - [ ] 8.3 Write `Projects/House-App/docs/runbook.md`. Generic content only:
    - what the box is
    - how to restart it (unplug for 10 seconds, then plug back in)
    - that the Honeywell app and the wall thermostat always work without it
    - where the backup key is kept (name the password manager, not the key)
    - what to do if the app says "can't connect"
  - [ ] 8.4 Print the runbook and keep it with the house documents, or tape it near the box
  - [ ] 8.5 Create `Projects/House-App/README.md` linking the PRD, both task lists and the runbook
  - [ ] 8.6 Commit and open a PR into `main`
