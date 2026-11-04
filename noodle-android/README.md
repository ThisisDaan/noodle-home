# Noodle for Android

Native client for the homepi/Noodle server on the Pi. Replaces the Home Assistant companion app.

- Live device list by room over `/api/ws` (no polling); toggle lights/switches, dim, change the thermostat target.
- The phone shows up in Noodle as a device (`phone:<id>`): battery, charging and a **Home** presence sensor (within 150 m of `HOMEPI_LAT`/`HOMEPI_LON`). Use it in flows like any sensor.
- Login trades the password once for a long-lived token (`POST /api/auth/app`); the password is not stored.

## Build

1. Install Android Studio, open this folder, let Gradle sync.
2. Run on your phone (USB debugging) or *Build > Build APK*.
3. Deploy the updated backend first (token login and `/api/phone/{id}`), then enter `http://192.168.1.104:8090` and the Noodle password in the app.
4. Settings > *Allow location* (choose "Allow all the time") for home/away.

Requires Android 11+ (minSdk 30). Plain HTTP is allowed because the server is on the LAN.
