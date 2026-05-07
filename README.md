# Adria Music Player

[![Python](https://img.shields.io/badge/Python-3-blue?logo=python&logoColor=white)](https://www.python.org/)
![GTK4](https://img.shields.io/badge/GTK-4-4a86cf?logo=gtk&logoColor=white)
![libadwaita](https://img.shields.io/badge/libadwaita-Adwaita-5c6bc0)
![Linux](https://img.shields.io/badge/Linux-Desktop-fcc624?logo=linux&logoColor=black)
![Arch Linux](https://img.shields.io/badge/Arch-makepkg-1793d1?logo=arch-linux&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Minimal personal music player for Linux built with Python, GTK4, and libadwaita. It is designed as a compact desktop player for local folders, with `mpv` handling playback, `mutagen` reading metadata and embedded cover art, and optional helpers for downloads and MPRIS integration.

The goal of this project is not to be a full music library manager. It is a small, focused desktop app with a lightweight interface and a workflow centered around local audio folders.

## Screenshot

No real screenshot is currently committed to the repository.

Expected path for the main UI capture:
`docs/screenshots/main-window.png`

See [docs/screenshots/README.md](docs/screenshots/README.md) for the screenshot placeholder and naming convention.

## Features

- Compact GTK4/libadwaita desktop player UI for Linux.
- Load a local folder and build a playlist from supported audio files.
- Read track title, artist, and embedded cover art from file metadata.
- Playback controls for previous, play/pause, next, stop, and shuffle.
- Progress bar with seek support.
- Dynamic styling from embedded cover art, with pywal fallback when available.
- Optional downloads through `yt-dlp` into the currently loaded folder.
- Automatic queueing of newly downloaded tracks into the current playlist.
- Optional MPRIS support through `mpv-mpris` for Waybar or desktop media controls.

## Tech Stack

- Python 3
- GTK4
- libadwaita
- `gi.repository` via PyGObject
- `mpv` JSON IPC
- `mutagen`
- CSS for UI styling
- Optional: `yt-dlp`, `ffmpeg`, `mpv-mpris`, `pywal`

## Requirements

Core runtime dependencies:

- Python 3
- `python-gobject`
- `gtk4`
- `libadwaita`
- `mpv`
- `python-mutagen`

Optional integrations:

- `yt-dlp` and `ffmpeg` for downloading audio from supported URLs
- `mpv-mpris` for MPRIS integration with Waybar or desktop controls
- `pywal` if you want theme colors to react to your system wal palette when no cover-based palette is available

On Arch Linux, the core dependencies can be installed with:

```bash
sudo pacman -S python python-gobject gtk4 libadwaita mpv python-mutagen
```

Optional packages:

```bash
sudo pacman -S yt-dlp ffmpeg mpv-mpris
```

## Installation

This repository includes packaging files compatible with `makepkg`. It is not documented here as an AUR package.

If you only want to run it locally from source, see the next section.

## Run from Source

Clone the repository and start the app with Python:

```bash
git clone https://github.com/AdriaBC06/adria-music-player.git
cd adria-music-player
python adria_music_player.py
```

If you specifically want to force Wayland:

```bash
GDK_BACKEND=wayland python adria_music_player.py
```

## Arch Linux Package

The repository ships with:

- `PKGBUILD`
- `.SRCINFO`
- `adria-music-player.desktop`

Build the package locally with:

```bash
makepkg -si
```

After installation, launch it with:

```bash
adria-music-player
```

## Usage

1. Open the app.
2. Click the folder button and choose a directory with supported audio files.
3. Use the playback controls to navigate the playlist.
4. Click the YouTube or Spotify button to download audio into the currently loaded folder.
5. If `mpv-mpris` is installed, media information can be exposed to MPRIS-aware tools such as Waybar.

Supported local audio extensions currently include:

- `.mp3`
- `.flac`
- `.ogg`
- `.wav`
- `.m4a`
- `.opus`

## Project Structure

```text
.
├── adria_music_player.py        # Main application logic
├── adria_music_player.css       # GTK styling template
├── adria-music-player.desktop   # Desktop entry
├── PKGBUILD                     # Arch Linux packaging
├── .SRCINFO                     # Generated Arch package metadata
├── docs/
│   ├── INSTALL.md
│   ├── TROUBLESHOOTING.md
│   └── screenshots/
└── README.md
```

## Troubleshooting

Common issues are documented in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

Quick notes:

- If playback does not start, verify that `mpv` is installed and available in `PATH`.
- If downloads fail, make sure both `yt-dlp` and `ffmpeg` are installed.
- If MPRIS controls do not appear in Waybar, verify that `mpv-mpris` is installed on your system.
- If the app does not pick up wal colors, confirm that your pywal cache exists at `~/.cache/wal/colors.json`.

## Roadmap

- Add a real UI screenshot to `docs/screenshots/main-window.png`.
- Improve error feedback around failed downloads and invalid URLs.
- Add a small settings surface for optional integrations and startup behavior.
- Package a proper application icon and install it with the desktop entry.
- Add lightweight automated checks beyond syntax validation.

## GitHub Metadata Suggestion

Suggested repository description:

`Minimal GTK4/libadwaita music player for Linux with mpv playback, metadata covers, and optional yt-dlp downloads.`

Suggested topics:

- `linux`
- `gtk4`
- `libadwaita`
- `python`
- `mpv`
- `music-player`
- `arch-linux`
- `desktop-app`
- `wayland`

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

## Author

Created by Adria.
