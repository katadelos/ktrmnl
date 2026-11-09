# ktrmnl

Turn a Kindle or Kobo into an e-ink dashboard. ktrmnl displays screens from a
TRMNL server, cycles through images stored on the reader, and accepts images
and notifications from scripts or home automations on your network.

Use it for a desk calendar, a weather display, a photo slideshow, or a status
screen. It runs alongside the reader's usual interface: exit ktrmnl to return
to your books.

## What can it display?

| Mode | What it does |
| --- | --- |
| **TRMNL** | Fetches dashboard images from your TRMNL server and refreshes on the server's schedule. |
| **Local images** | Cycles through a folder of images, with an adjustable interval and optional shuffle. Works offline. |
| **HTTP push** | Displays the latest image sent to the reader over your local network. |
| **Interrupt** | Shows temporary text alerts over a TRMNL dashboard, then returns to the dashboard when the alert expires or is dismissed. |

Local images and HTTP push do not need a TRMNL server or API token.

## Getting started

You need a supported Kindle or Kobo running its stock firmware with the k2 SDK
installed. Kindle devices must be jailbroken.

1. Install the `ktrmnl` package using the k2 SDK package manager.
2. Open **ktrmnl** from k2's Device page or cog menu. On Kobo, you can also
   launch it from NickelMenu.
3. Choose your language and complete the introduction.
4. For network content, open **Network → Select Wi-Fi network** and connect.
   You can reuse a saved network or enter a password on the reader.
5. Open **Content → Content source**, choose a mode, and configure it as
   described below.

Tap the display or press **Menu** to open the menu. Touch and physical navigation
buttons are supported; use the direction buttons and **Select** to navigate
menus and the on-screen keyboard. **Back** returns to the previous page.

## Connect a TRMNL dashboard

Choose **TRMNL** in Content settings, then enter your **Server URL** and **API
token**. Use the server's base address, such as `https://trmnl.example.com`,
without an `/api/display` path. The server supplies the dashboard image and
its refresh interval.

Choose **Interrupt** instead if you also want to receive text alerts while
showing that dashboard. It uses the same server settings.

## Show local images

Create an `images` folder at the root of the reader's USB storage and copy your
images into it. Choose **Local images** in Content settings. You can change the
folder, refresh interval, and shuffle setting there.

The default folder is `/mnt/us/images` on Kindle or `/mnt/onboard/images` on
Kobo. Supported formats are PNG, JPEG, GIF, BMP, and WebP.

## Send content from another device

Connect the sender and reader to the same local network. In the examples below,
replace `READER_IP` with the reader's Wi-Fi address, available from your router's
connected-device list.

### Send an image

Select **HTTP push** on the reader, then send an image from your computer or
an automation:

```sh
curl --data-binary @dashboard.png \
  -H 'Content-Type: image/png' \
  http://READER_IP:8080/push/image
```

Each successful push replaces the displayed image. Pushed images are temporary
and are discarded when you exit the app.

### Send an alert

Select **Interrupt** on the reader, then send a message:

```sh
curl -H 'Content-Type: application/json' \
  -d '{"title":"Home","message":"Front door opened","expires_in":30}' \
  http://READER_IP:8080/push/interrupt
```

This shows the alert for 30 seconds. Dismissing it early also returns to the
underlying dashboard.

Only the endpoint for the selected mode is active. These endpoints have no
authentication; use them on a trusted local network.

## Display, battery, and settings

- **Display** controls rotation, dark mode, and the frontlight on readers that
  have one. The frontlight is off by default.
- **Sleep between updates** lets supported readers sleep between TRMNL or
  local-image updates while keeping the last image on screen. The reader wakes
  for the next update. The power button also provides manual sleep and wake.
- **HTTP push and Interrupt keep the reader awake** to receive content. They
  cannot receive anything while the reader is asleep.
- **System** lets you change the language, dashboard name, and low-battery
  warning threshold, or reset the app's settings.
- **Exit ktrmnl** in the main menu returns to the reader's normal interface.

Settings are saved on the reader in `/mnt/us/ktrmnl/config.json` on Kindle or
`/mnt/onboard/ktrmnl/config.json` on Kobo. Most settings can be changed in the
app; [config.example.json](config.example.json) lists the configuration keys.

## Development

The host simulator runs the same interface with simulated device and Wi-Fi
backends. With Python 3.11 or later and `uv` installed:

```sh
uv sync --python 3.11
uv run ktrmnl-sim --first-run
uv run pre-commit install
```

Use `--controls` to open the simulator's display and content controls, or
`--config /tmp/ktrmnl-preview.json` for a separate set of preview settings.

Run formatting, lint, and dead-code checks with
`uv run pre-commit run --all-files`. Run the Python tests with
`QT_QPA_PLATFORM=offscreen uv run python -m unittest discover -s tests`.
