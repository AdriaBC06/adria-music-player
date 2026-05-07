# Troubleshooting

## The app opens but playback does not work

- Check that `mpv` is installed.
- Confirm that `mpv` is available in `PATH`:

```bash
command -v mpv
```

## The selected folder is rejected

- The folder must contain at least one supported audio file.
- Supported extensions are `.mp3`, `.flac`, `.ogg`, `.wav`, `.m4a`, and `.opus`.

## Metadata or cover art does not appear

- The file may not include embedded tags or artwork.
- The app falls back to the filename and a placeholder artwork state when metadata is missing.

## Download buttons fail

- Verify that both `yt-dlp` and `ffmpeg` are installed:

```bash
command -v yt-dlp
command -v ffmpeg
```

- The app expects a standard YouTube or Spotify URL format.
- Downloads are saved into the currently loaded music folder.

## MPRIS or Waybar integration does not appear

- Install `mpv-mpris`.
- Restart the app after installing it so `mpv` can load the MPRIS script.

## pywal colors are not applied

- `pywal` is optional.
- If you use it, make sure `~/.cache/wal/colors.json` exists and contains valid JSON.
- When embedded cover art is available, the app prefers a cover-derived palette over wal colors.

## The app looks wrong on X11

- The app is intended for Linux desktop use and is especially suited to Wayland setups.
- If you want to force Wayland, launch it with:

```bash
GDK_BACKEND=wayland python adria_music_player.py
```
