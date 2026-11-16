# Roadmap

Ordered from easy to hard. "Hard" means more design and hardware testing, not more code.
Every user-facing item gets a quick "how should it feel" check before it is built.

## Tier 1: small and self-contained

1. **"Press Search" empty states** on Devices and Integrations, so search-only discovery never looks broken.
2. **History retention** dropdown in System (e.g. keep 7 / 30 / 90 / 365 days).
3. **Update banner** (a "Check for updates" button exists on System; the banner is not there yet): compare with the latest GitHub release, show the changelog. Notify only.
4. **Backup and restore** (done): download a zip of `<data>/config/` + `noodle.db`, upload one to restore. Add-on volumes join later (item 21).
5. **Scenes**: "Save current state" becomes a scene. Stored as a flow, shown in the app as a scene.
6. **Harden Noodle itself**: runs as a non-root user; documented container setup with a read-only filesystem and all capabilities dropped.
7. **Themes** (done; System → Appearance): a picker with Noodle Light/Dark and a set of ready-made daisyUI themes (Dracula, Nord, ...), hub-wide. A free colour editor was tried and dropped in favour of the list.

## Tier 2: real features, no new hardware

8. **Flow run trace**: per run, each node's input and output and why the run stopped, as a timeline in the flow editor.
9. **Household users**: replaces the single shared admin login.
   - Roles: Admin (everything) and Member (control devices, see dashboards; no flow or settings edits).
   - History records who did what.
   - Later options: members limited to some areas or devices, a Guest role, per-user themes.
10. **One-click update** (exists for Docker installs from the published image; database backup first and pip installs are still to do): back up the database, install the new wheel, restart, roll back if it doesn't come up healthy.
11. **Home Assistant import**: devices, areas and simple automations over HA's local API. Imported flows start switched off; a report lists what didn't convert.
12. **Energy view** from the plugs and meters Noodle already reads.
13. **ESPHome plugin** over its local native API.

## Tier 3: add-on system (Noodle as a Docker client, no custom OS)

14. **`noodle-agent`**: a small separate service that owns `docker.sock`. Noodle never touches the socket; it holds a token for the agent's HTTP API. Actions: start, stop, update, remove, logs, install recipe.
15. **Agent policy**, enforced on every container whatever the request says:
    - only containers labelled `noodle.addon=*`
    - no privileged mode, host PID or host IPC; `no-new-privileges` always on
    - bind mounts only under `/srv/noodle/addons/<name>/`
    - devices only from `/dev/serial/by-id/*`
    - capabilities from an allowlist
    - host networking only when the recipe asks for it
    - If Noodle is hacked, the attacker can manage add-ons from the approved list, nothing more: no root, no other containers, no rest of the disk.
16. **Recipes** in the agent's read-only folder (Noodle can't write them): image pinned to a digest, ports, volumes, devices, a settings form, an optional plugin link.
17. **Add-ons tab in Integrations**: install from the catalog with a settings form and a USB picker; status and logs. Containers the user already runs are shown read-only.
18. **Automatic setup, then confirm**: installing an add-on fills in the matching plugin (Mosquitto → MQTT plugin, Zigbee2MQTT → Zigbee) and shows a summary with Undo.
19. **Add-on updates**: pull, recreate, roll back to the previous image if unhealthy.
20. **Custom containers**: any image, boxed in by the same policy.
21. **Add-on volumes in backups** (extends item 4).
22. **First catalog**: Mosquitto, Zigbee2MQTT, ESPHome dashboard, Matter server, Frigate.
23. **Elevated recipe level**: catalog-only recipes that need `NET_ADMIN`, `/dev/net/tun` or host networking. Labelled "Elevated: can change the Pi's networking" in the app. Custom containers never get it.
24. **Tailscale add-on** (replaces a remote-access tutorial): Install → Sign in button + QR → "Reachable at `https://noodle.<tailnet>.ts.net`". Uses `tailscale serve` for HTTPS to Noodle only; reaching the whole Pi is a separate toggle, off by default.
25. **Headscale and wg-easy add-ons**: remote access with nothing in the cloud (self-hosted coordinator, or plain WireGuard with a port forward).
26. **Optional rootless mode**: rootless Docker or Podman, documented with its USB caveats.

## Tier 4: needs hardware and deep design

27. **Z-Wave** via a Z-Wave JS add-on, plus a plugin and an inclusion screen.
28. **Cameras**: RTSP snapshots and motion as a flow trigger (Frigate add-on). Live view later.
29. **Matter bridge mode**: expose Noodle devices to Apple Home, Google and Alexa locally. The voice-assistant answer without the cloud.
30. **Vacuums and thermostats**, one brand at a time, local control only.
31. **Third-party plugin installer** from a git URL with pinned versions, once the plugin API is stable.
32. **Confirm step for risky devices** (locks, heaters), so a hijacked session can't trigger them silently.

## Never

- YAML as a user interface.
- A custom OS or Supervisor. Noodle stays an ordinary Docker client on a normal OS.
- Cloud-only integrations.
- Jinja or any templating language in automations; add a node instead.
- Splitting one device into many entities.
- Background auto-discovery.
- A dashboard card store.
- Monthly breaking changes; migrations are tested and safe to run twice.
- A separate "statistics" system next to history.

## Suggested order

1. Backup and restore (4), then flow trace (8).
2. HA import (11) and one-click update (10).
3. Add-on system (14–26).
4. Tier 4.
