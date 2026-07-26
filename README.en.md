# eversolo-screen

Now playing display for Eversolo streamers (DMP-A6, A8, A10) on a Raspberry Pi + HDMI screen. Album art, title, audio quality, artist biographies and production credits, driven by an infrared remote.

[Français](README.md) · [Español](README.es.md) · [Deutsch](README.de.md)

## Features

- Album art, title, artist, album, progress, clock, ambient glow derived from the artwork
- Audio quality chips: sample rate, bit depth, bitrate (real Eversolo formats handled)
- 3-page info panel: artist biography, album (description, tracks, durations), production (credits, label, studios)
- Learning infrared remote: 7 actions pairable with any remote you own
- Optional infrared blaster: the Pi learns and replays commands to your TV or amp
- Kiosk mode at boot, password-protected admin pages
- 4 languages: French, English, Spanish, German
- One-click update from the interface

## Hardware

| Item | Minimum | Recommended |
|---|---|---|
| Raspberry Pi | Pi 3 | Pi 4, 2 GB |
| SD card | 16 GB | Class A1 |
| Power supply | | Official Raspberry |
| Network | Wi-Fi | Ethernet |
| IR receiver (optional) | VS1838B or TSOP38238 | |
| IR LED (optional) | 940 nm LED + 220 Ω resistor | KY-005 module |

The Eversolo is controlled over the network (API port 9529): no sensor needed on the streamer.

## Install

### Automatic (recommended)

1. Raspberry Pi Imager: Raspberry Pi OS Lite 64-bit, SSH enabled, password authentication
2. With the card still mounted:

```bash
curl -O https://raw.githubusercontent.com/kofekod23/eversolo-screen/main/tools/prepare-sd.sh
bash prepare-sd.sh
```

3. Boot the Pi. After 10 to 15 minutes, open `http://PI_IP:8080`: the assistant detects the Eversolo and creates the admin password.

### Manual (SSH)

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/kofekod23/eversolo-screen.git
cd eversolo-screen && ./install.sh --kiosk --ir
sudo reboot
```

Stackable options: `--kiosk` (TV display), `--ir` (remote receiver), `--ir-tx` (blaster), `--ram` (logs and caches in RAM, spares the SD card).

## Remote

`http://PI_IP:8080/remote`: sensor wiring diagram, detection light, live test, pairing of the 7 actions (play/pause, tracks, volume, mute, info). With the info panel open, volume keys scroll the text and track keys turn the pages.

## Data sources

| Data | Sources |
|---|---|
| Artist and album identity | MusicBrainz (the playing album disambiguates homonyms) |
| Biographies | TheAudioDB, Last.fm, Wikipedia via Wikidata |
| Tracks, credits, studios | MusicBrainz, Discogs, Genius (current track) |

Everything works without any key. Optional keys on `/config` widen coverage: Last.fm (free), Discogs (free personal token, credits of recent releases), TheAudioDB.

## Update

Button on `/config` when a new version is published, or over SSH: `./update.sh`. Configuration and password preserved.

## License

[CC BY-NC-SA 4.0](LICENSE.en.md): free to use and modify, selling and monetizing forbidden.

## Troubleshooting

Full step-by-step guide (French): [INSTALL.md](INSTALL.md). Forgotten password: `venv/bin/python tools/motdepasse.py`.
