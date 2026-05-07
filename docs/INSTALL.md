# Installation

## Arch Linux

Install the core runtime dependencies:

```bash
sudo pacman -S python python-gobject gtk4 libadwaita mpv python-mutagen
```

Optional packages:

```bash
sudo pacman -S yt-dlp ffmpeg mpv-mpris
```

Build and install the packaged version from this repository:

```bash
makepkg -si
```

## Run From Source

```bash
git clone https://github.com/AdriaBC06/adria-music-player.git
cd adria-music-player
python adria_music_player.py
```

To explicitly run on Wayland:

```bash
GDK_BACKEND=wayland python adria_music_player.py
```

## Notes

- `mpv` is required for playback.
- `mutagen` is required for metadata and embedded cover extraction.
- `yt-dlp` and `ffmpeg` are only required if you want the download buttons to work.
- `mpv-mpris` is optional and only affects MPRIS integration.
- `pywal` is optional and only affects theme fallback behavior.
