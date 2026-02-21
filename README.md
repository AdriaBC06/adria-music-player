# Wal Player

Minimal floating desktop music player for Linux (Wayland/Hyprland), built with:

- Python 3
- GTK4 + libadwaita (`gi.repository`)
- `mpv` via IPC socket
- `mutagen` for metadata/cover extraction
- pywal dynamic theme sync

## Features

- Floating widget-style player UI
- Folder-based playlist loading
- Cover, title, artist, progress bar
- Previous/Next/Play/Pause/Stop/Shuffle
- Download from YouTube/Spotify via `yt-dlp`
- Auto-queue downloaded songs into current playlist
- Theme sync from song cover colors (fallback to wal/system colors)
- Waybar/MPRIS support through `mpv-mpris`

## Requirements (Arch Linux)

Install packages:

```bash
sudo pacman -S python python-gobject gtk4 libadwaita mpv python-mutagen yt-dlp ffmpeg mpv-mpris
```

## Run

```bash
GDK_BACKEND=wayland python wal_player.py
```

## Notes

- If a song has embedded cover art, app colors are derived from it.
- If no cover exists, app uses wal/system theme fallback.
- For Waybar media module detection, `mpv-mpris` must be installed.

## Files

- `wal_player.py`: app logic (MVC + theming + mpv/yt-dlp integration)
- `wal_player.css`: visual styling template
