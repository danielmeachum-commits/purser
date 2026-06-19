# budget-eink (Pi client)

Pulls a pre-rendered 800×480 PNG from the FastAPI service and pushes it to
a Pimoroni Inky Impression 7.3". All layout and palette quantization
happens server-side; the Pi just blits the bytes to the panel.

Two refresh paths run in parallel:

- **`budget-eink.timer`** — hourly safety-net oneshot pull.
- **`budget-eink-listener.service`** — long-running daemon that subscribes
  to the API's WebSocket; refreshes on `eink.refresh` (dashboard button)
  and on any data-change event (transactions, accounts, categories,
  savings goals). Debounced + 60s cooldown so the panel isn't asked to
  redraw faster than it physically can (~30s per refresh).

## Hardware

- Raspberry Pi Zero 2 W
- Pimoroni Inky Impression 7.3"
- Raspberry Pi OS Trixie

## One-time Pi setup

The unit files assume user `hobbes` and the Pimoroni installer venv at
`~/.virtualenvs/pimoroni`. If yours differ, edit the `User=` and
`ExecStart=` lines in `budget-eink.service` and `budget-eink-listener.service`.

1. **Pimoroni inky lib** (one-line installer enables SPI + drops a venv at
   `~/.virtualenvs/pimoroni` with `inky` + Pillow already installed). Then
   add the WebSocket library the listener needs:

    ```bash
    ~/.virtualenvs/pimoroni/bin/pip install -r requirements.txt
    ```

2. **Tailscale** (so the Pi reaches the server without LAN/NAT pain):

    ```bash
    curl -fsSL https://tailscale.com/install.sh | sh
    sudo tailscale up
    ```

3. **Copy this directory to the Pi** at `~/budget-eink/`:

    ```bash
    rsync -a pi/ <user>@<pi-host>:/home/<user>/budget-eink/
    ```

4. **Create `/etc/budget-eink/config.env`** with the API URL and a token
   (generate one at `/admin/tokens` — `read` scope is enough for the
   poll path; the manual-refresh button uses the dashboard's own admin
   session, so the Pi token does *not* need admin):

    ```env
    BUDGET_API_URL=https://<server-tailscale-name>/api
    BUDGET_API_TOKEN=bgt_xxxxxxxxxxxxxxxx
    ```

    Lock it down (mode 0600, owned by the service user):

    ```bash
    sudo mkdir -p /etc/budget-eink
    sudo install -m 600 config.env /etc/budget-eink/config.env
    sudo chown <user>:<user> /etc/budget-eink/config.env
    ```

5. **Install the systemd units** and enable both the timer + the listener:

    ```bash
    sudo cp ~/budget-eink/budget-eink.service          /etc/systemd/system/
    sudo cp ~/budget-eink/budget-eink.timer            /etc/systemd/system/
    sudo cp ~/budget-eink/budget-eink-listener.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now budget-eink.timer
    sudo systemctl enable --now budget-eink-listener.service
    ```

## Manual refresh / debugging

```bash
# One-shot refresh from the Pi
sudo systemctl start budget-eink.service

# Tail the hourly job
journalctl -u budget-eink.service -f

# Tail the live listener
journalctl -u budget-eink-listener.service -f

# Run the script directly (useful when iterating)
BUDGET_API_URL=... BUDGET_API_TOKEN=... \
  ~/.virtualenvs/pimoroni/bin/python ~/budget-eink/client.py
```

The dashboard's **Refresh Inky** button (top-right, admin-only) calls
`POST /eink/refresh` on the API, which broadcasts an `eink.refresh`
WebSocket event the listener picks up and acts on.

## How refresh cadence works

- **Hourly timer** is the floor — `OnCalendar=hourly`, fires on the hour
  and once 30s after boot. Change the schedule by editing
  `budget-eink.timer` (e.g. `OnCalendar=*:0/30` for every 30 minutes).
- **Listener** reacts to any data-change event broadcast on `/ws`. A 5s
  debounce coalesces bursts; a 60s cooldown protects the panel.
