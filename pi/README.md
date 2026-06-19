# budget-eink (Pi client)

Pulls a pre-rendered 800×480 PNG from the FastAPI service and pushes it to
a Pimoroni Inky Impression 7.3". All layout, color quantization, and
Floyd-Steinberg dithering happens server-side; the Pi just blits the
bytes to the panel.

## Hardware

- Raspberry Pi Zero 2 W
- Pimoroni Inky Impression 7.3" (7-color, 800×480)
- Raspberry Pi OS Trixie

## One-time Pi setup

1. **Install the Pimoroni `inky` library** (also enables SPI + installs Pillow):

    ```bash
    pip install --user inky[rpi]
    ```

    Or, if you used Pimoroni's one-line installer, it should already be in place.

2. **Tailscale** (so the Pi can reach the server without LAN/NAT pain):

    ```bash
    curl -fsSL https://tailscale.com/install.sh | sh
    sudo tailscale up
    ```

3. **Copy this directory to the Pi** at `/home/pi/budget-eink/`:

    ```bash
    rsync -a pi/ pi@<pi-hostname>:/home/pi/budget-eink/
    ```

4. **Create `/etc/budget-eink/config.env`** with the API URL and a read token
   (generate one in the admin UI at `/admin/tokens` with scope `read`):

    ```env
    BUDGET_API_URL=http://<server-tailscale-name>:8000
    BUDGET_API_TOKEN=bgt_xxxxxxxxxxxxxxxx
    ```

    Lock it down:

    ```bash
    sudo mkdir -p /etc/budget-eink
    sudo install -m 600 config.env /etc/budget-eink/config.env
    sudo chown pi:pi /etc/budget-eink/config.env
    ```

5. **Install the systemd units** and enable the hourly timer:

    ```bash
    sudo cp /home/pi/budget-eink/budget-eink.service /etc/systemd/system/
    sudo cp /home/pi/budget-eink/budget-eink.timer   /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now budget-eink.timer
    ```

## Manual refresh / debugging

```bash
# Trigger a one-shot refresh
sudo systemctl start budget-eink.service

# Tail the logs
journalctl -u budget-eink.service -f

# Run the script directly (useful when iterating on the layout)
BUDGET_API_URL=... BUDGET_API_TOKEN=... python3 /home/pi/budget-eink/client.py
```

## How refresh cadence works

`budget-eink.timer` fires hourly (`OnCalendar=hourly`) plus once 30s after boot.
The Inky takes ~30s to refresh the panel, so polling faster than every few
minutes is pointless. Adjust the `OnCalendar=` line if you want a different
cadence (e.g. `OnCalendar=*:0/30` for every 30 minutes).
