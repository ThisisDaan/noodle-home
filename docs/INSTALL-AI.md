# Installing Noodle (instructions for an AI assistant)

A user may have asked you to install Noodle on their computer. Follow this file. Ask the user before you install system software (Python, Bun, Docker) and tell them what you are about to run.

Noodle is a local smart home hub. It runs on the user's machine and opens in a browser at `http://localhost:8090`. It needs no cloud account.

## 1. Pick the method

| The user's machine | Method |
|---|---|
| Linux (Raspberry Pi, mini PC, server) | **Docker** (recommended, step 2a) |
| Windows or macOS | **run script** (step 2b). Docker is not suitable: Noodle needs the host network to find devices, which Docker Desktop does not provide. |
| Linux without Docker | run script (step 2b) |

Check what exists first: `docker --version`, `python --version` (needs 3.11+), `bun --version`, `git --version`.

## 2a. Docker (Linux)

```bash
git clone https://github.com/ThisisDaan/noodle-home.git
cd noodle-home/noodle
docker compose up -d
```

## 2b. Run script (Windows, macOS, Linux)

```bash
git clone https://github.com/ThisisDaan/noodle-home.git
cd noodle-home/noodle
```

Then run the script for the platform. It creates a virtual environment, installs the Python packages, builds the interface once, and starts the hub. It stays in the foreground until Ctrl+C.

- Windows: `run.bat`
- macOS / Linux: `./run.sh`

Missing prerequisites (the script stops and says which):

- Python 3.11+: Windows `winget install Python.Python.3.12`; macOS `brew install python@3.12`; Linux: the package manager.
- Bun: Windows `winget install Oven-sh.Bun`; macOS/Linux `curl -fsSL https://bun.sh/install | bash`. A new terminal may be needed afterwards so the command is found.
- Git: Windows `winget install Git.Git`.

## 3. Check that it works

Open `http://localhost:8090` (or `http://<machine-ip>:8090` from another device). A setup wizard appears: home name and location, which services the user has, and a first device to pair. Every step can be skipped. Tell the user to continue there; **everything is configured in the app**, no files need editing.

If the page does not load:

- Look at the terminal output of the script or `docker compose logs noodle`.
- Port 8090 busy: set `NOODLE_PORT` to another number and start again.
- Windows firewall prompt: allow Python on private networks, so other devices on the home network can reach the hub.

## 4. Keep it running

- Docker: already restarts on boot.
- Run script: it stops when the terminal closes. For an always-on setup on Linux use [`noodle.service`](../noodle/noodle.service) (systemd); on Windows, Task Scheduler with `run.bat` at logon.

## 5. Update

- Docker: **System → Check for updates** in the app.
- Run script: `run.bat --update` or `./run.sh --update`.

## Data and safety

- All settings, flows and history are in `noodle/data/`. Back this folder up before an update.
- Do not edit YAML files in `data/config/` unless the user asks. Flow-writing rules for AIs are in [AI.md](AI.md).
- Do not enter the user's passwords or tokens for them; the wizard asks them directly.
