# Contributing

Thanks for taking a look at the project.

## Scope

This is a small personal Linux desktop app. Please keep contributions focused, practical, and aligned with the current direction of the project.

Good contribution examples:

- Bug fixes
- Small UI polish improvements
- Packaging fixes
- Documentation improvements
- Better error handling

## Development Notes

- The app is written in Python with GTK4 and libadwaita.
- `mpv` is used for playback through IPC.
- Optional integrations such as `yt-dlp`, `ffmpeg`, `mpv-mpris`, and `pywal` should remain optional unless there is a strong reason to change that.

## Before Opening a PR

- Make sure Python files still compile:

```bash
python -m py_compile adria_music_player.py
```

- If you modify `PKGBUILD`, regenerate `.SRCINFO` when `makepkg` is available:

```bash
makepkg --printsrcinfo > .SRCINFO
```
