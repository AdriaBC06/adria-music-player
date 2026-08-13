#!/usr/bin/env python3
#
# Copyright (C) 2026 Adrià
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. See <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Adria Music Player: floating music player for GTK4/libadwaita on Wayland.

Architecture:
- Model: PlayerModel
- View: MusicPlayerView
- Controller: MusicPlayerController
"""

import json
import os
import random
import re
import shutil
import socket
import subprocess
import tempfile
import threading
from urllib.parse import urlparse
from dataclasses import dataclass, field
from pathlib import Path

import gi
from mutagen import File as MutagenFile


gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402


WAL_COLORS_PATH = Path.home() / ".cache" / "wal" / "colors.json"
CSS_TEMPLATE_PATH = Path(__file__).with_name("adria_music_player.css")
IPC_SOCKET_PATH = Path(tempfile.gettempdir()) / f"adria-music-player-mpv-{os.getpid()}.sock"
APP_ID = "com.adria.musicplayer"
AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".opus"}
COVER_SIZE = 100
WINDOW_WIDTH = 388
WINDOW_HEIGHT = 110
TEXT_VIEW_CHARS = 26
MARQUEE_TICK_MS = 140
DEFAULT_TITLE = "No file loaded"
DEFAULT_ARTIST = "Unknown artist"


@dataclass
class TrackState:
    path: str = ""
    folder_path: str = ""
    playlist: list[str] = field(default_factory=list)
    title: str = DEFAULT_TITLE
    artist: str = DEFAULT_ARTIST
    cover_data: bytes | None = None
    is_playing: bool = False
    progress_fraction: float = 0.0


class WalThemeManager:
    """Loads pywal colors and applies a tokenized external CSS template."""

    def __init__(self):
        self.monitor = None
        self.css_provider = Gtk.CssProvider()
        self.cover_overrides = None

        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display,
                self.css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

        self.apply_theme()
        self._setup_monitor()

    @staticmethod
    def _hex_to_rgba(hex_color: str, alpha: float) -> str:
        clean = hex_color.lstrip("#")
        if len(clean) != 6:
            return f"rgba(26, 26, 26, {alpha})"
        try:
            r = int(clean[0:2], 16)
            g = int(clean[2:4], 16)
            b = int(clean[4:6], 16)
        except ValueError:
            return f"rgba(26, 26, 26, {alpha})"
        return f"rgba({r}, {g}, {b}, {alpha})"

    @staticmethod
    def _hex_to_rgb_csv(hex_color: str) -> str:
        clean = hex_color.lstrip("#")
        if len(clean) != 6:
            return "26, 26, 26"
        try:
            r = int(clean[0:2], 16)
            g = int(clean[2:4], 16)
            b = int(clean[4:6], 16)
        except ValueError:
            return "26, 26, 26"
        return f"{r}, {g}, {b}"

    @staticmethod
    def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
        r, g, b = rgb
        return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"

    @staticmethod
    def _mix_rgb(a: tuple[int, int, int], b: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
        ratio = max(0.0, min(1.0, ratio))
        return (
            int(a[0] * (1.0 - ratio) + b[0] * ratio),
            int(a[1] * (1.0 - ratio) + b[1] * ratio),
            int(a[2] * (1.0 - ratio) + b[2] * ratio),
        )

    @staticmethod
    def _luminance(rgb: tuple[int, int, int]) -> float:
        r, g, b = rgb
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def _extract_cover_palette(self, image_data: bytes | None) -> dict | None:
        if not image_data:
            return None

        loader = GdkPixbuf.PixbufLoader()
        try:
            loader.write(image_data)
            loader.close()
            pixbuf = loader.get_pixbuf()
            if pixbuf is None:
                return None
            small = pixbuf.scale_simple(40, 40, GdkPixbuf.InterpType.BILINEAR)
            if small is None:
                return None
        except GLib.Error:
            return None

        width = small.get_width()
        height = small.get_height()
        channels = small.get_n_channels()
        rowstride = small.get_rowstride()
        pixels = small.get_pixels()
        if channels < 3:
            return None

        total = 0
        acc_r = acc_g = acc_b = 0
        best_rgb = None
        best_score = -1.0

        for y in range(height):
            row = y * rowstride
            for x in range(width):
                idx = row + x * channels
                r = pixels[idx]
                g = pixels[idx + 1]
                b = pixels[idx + 2]
                if channels >= 4:
                    a = pixels[idx + 3]
                    if a < 24:
                        continue

                acc_r += r
                acc_g += g
                acc_b += b
                total += 1

                c_max = max(r, g, b)
                c_min = min(r, g, b)
                saturation = (c_max - c_min) / max(c_max, 1)
                score = saturation * c_max
                if score > best_score:
                    best_score = score
                    best_rgb = (r, g, b)

        if total == 0:
            return None

        avg_rgb = (acc_r // total, acc_g // total, acc_b // total)
        accent_rgb = best_rgb or avg_rgb

        bg_rgb = self._mix_rgb(avg_rgb, (0, 0, 0), 0.55)
        fg_rgb = (245, 245, 245) if self._luminance(bg_rgb) < 130 else (22, 22, 22)

        color0 = self._mix_rgb(bg_rgb, (0, 0, 0), 0.35)
        color2 = self._mix_rgb(accent_rgb, (255, 255, 255), 0.15)
        color4 = accent_rgb
        color5 = self._mix_rgb(accent_rgb, (255, 255, 255), 0.28)
        color6 = self._mix_rgb(accent_rgb, (255, 255, 255), 0.20)
        color7 = self._mix_rgb(bg_rgb, (255, 255, 255), 0.45)
        color8 = self._mix_rgb(bg_rgb, (255, 255, 255), 0.18)

        return {
            "background": self._rgb_to_hex(bg_rgb),
            "foreground": self._rgb_to_hex(fg_rgb),
            "color0": self._rgb_to_hex(color0),
            "color2": self._rgb_to_hex(color2),
            "color4": self._rgb_to_hex(color4),
            "color5": self._rgb_to_hex(color5),
            "color6": self._rgb_to_hex(color6),
            "color7": self._rgb_to_hex(color7),
            "color8": self._rgb_to_hex(color8),
        }

    def _load_wal_colors(self) -> dict:
        fallback = {
            "background": "#1e1e1e",
            "foreground": "#f5f5f5",
            **{f"color{i}": "#444444" for i in range(16)},
        }
        try:
            with WAL_COLORS_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            colors = data.get("colors", {})
            if not colors:
                return fallback
            for key in fallback:
                colors.setdefault(key, fallback[key])
            return colors
        except (OSError, json.JSONDecodeError):
            return fallback

    def _load_template(self) -> str:
        try:
            return CSS_TEMPLATE_PATH.read_text(encoding="utf-8")
        except OSError:
            return "window#adria-music-player-window { background: __WAL_WINDOW_BG__; color: __WAL_FOREGROUND__; }"

    def _build_css(self, colors: dict) -> str:
        replacements = {
            "__WAL_BACKGROUND__": colors["background"],
            "__WAL_FOREGROUND__": colors["foreground"],
            "__WAL_COLOR0__": colors["color0"],
            "__WAL_COLOR1__": colors["color1"],
            "__WAL_COLOR2__": colors["color2"],
            "__WAL_COLOR3__": colors["color3"],
            "__WAL_COLOR4__": colors["color4"],
            "__WAL_COLOR5__": colors["color5"],
            "__WAL_COLOR6__": colors["color6"],
            "__WAL_COLOR7__": colors["color7"],
            "__WAL_COLOR8__": colors["color8"],
            "__WAL_COLOR9__": colors["color9"],
            "__WAL_COLOR10__": colors["color10"],
            "__WAL_COLOR11__": colors["color11"],
            "__WAL_COLOR12__": colors["color12"],
            "__WAL_COLOR13__": colors["color13"],
            "__WAL_COLOR14__": colors["color14"],
            "__WAL_COLOR15__": colors["color15"],
            "__WAL_WINDOW_BG__": self._hex_to_rgba(colors["background"], 0.85),
            "__WAL_CARD_BG__": self._hex_to_rgba(colors["color8"], 0.35),
            "__WAL_BUTTON_BG__": self._hex_to_rgba(colors["color0"], 0.60),
            "__WAL_TEXT_MUTED__": self._hex_to_rgba(colors["foreground"], 0.75),
            "__WAL_BORDER_SOFT__": self._hex_to_rgba(colors["color7"], 0.22),
            "__WAL_BORDER_MED__": self._hex_to_rgba(colors["color7"], 0.28),
            "__WAL_SHADOW__": self._hex_to_rgba(colors["color0"], 0.36),
            "__WAL_PROGRESS_BG__": self._hex_to_rgba(colors["color0"], 0.45),
            "__WAL_SLIDER_BORDER__": self._hex_to_rgba(colors["background"], 0.60),
            "__WAL_SLIDER_SHADOW__": self._hex_to_rgba(colors["color0"], 0.40),
            "__WAL_HOVER_BG__": self._hex_to_rgba(colors["color6"], 0.82),
        }
        replacements["__WAL_BACKGROUND_RGB__"] = self._hex_to_rgb_csv(colors["background"])
        replacements["__WAL_FOREGROUND_RGB__"] = self._hex_to_rgb_csv(colors["foreground"])
        for i in range(16):
            replacements[f"__WAL_COLOR{i}_RGB__"] = self._hex_to_rgb_csv(colors[f"color{i}"])

        css = self._load_template()
        for token, value in replacements.items():
            css = css.replace(token, value)
        return css

    def apply_theme(self):
        colors = self._load_wal_colors()
        if self.cover_overrides:
            colors = {**colors, **self.cover_overrides}
        css = self._build_css(colors)
        self.css_provider.load_from_data(css.encode("utf-8"))

    def set_cover_theme(self, image_data: bytes | None):
        self.cover_overrides = self._extract_cover_palette(image_data)
        self.apply_theme()

    def _on_wal_file_changed(self, _monitor, file, _other_file, event_type):
        if file and file.get_basename() != WAL_COLORS_PATH.name:
            return
        if event_type in {
            Gio.FileMonitorEvent.CHANGED,
            Gio.FileMonitorEvent.CREATED,
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.ATTRIBUTE_CHANGED,
        }:
            self.apply_theme()

    def _setup_monitor(self):
        wal_file = Gio.File.new_for_path(str(WAL_COLORS_PATH))
        try:
            self.monitor = wal_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self.monitor.connect("changed", self._on_wal_file_changed)
        except GLib.Error:
            wal_dir = Gio.File.new_for_path(str(WAL_COLORS_PATH.parent))
            try:
                self.monitor = wal_dir.monitor_directory(Gio.FileMonitorFlags.NONE, None)
                self.monitor.connect("changed", self._on_wal_file_changed)
            except GLib.Error:
                self.monitor = None


class MPVController:
    """Controls mpv through JSON IPC over UNIX socket."""

    def __init__(self):
        self.process = None
        self.socket_path = str(IPC_SOCKET_PATH)
        self._request_id = 1
        self.mpris_script_path = self._find_mpris_script()

    @staticmethod
    def _find_mpris_script() -> str | None:
        candidates = [
            "/usr/share/mpv/scripts/mpris.so",
            "/usr/lib/mpv/scripts/mpris.so",
            "/usr/share/mpv/scripts/mpris.lua",
            "/usr/lib/mpv/scripts/mpris.lua",
        ]
        for path in candidates:
            if Path(path).is_file():
                return path
        return None

    @staticmethod
    def _mpv_exists() -> bool:
        return shutil.which("mpv") is not None

    def _send_command(self, command):
        if self.process is None or self.process.poll() is not None:
            return None

        payload = {"command": command, "request_id": self._request_id}
        self._request_id += 1

        for _ in range(3):
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(0.25)
                    client.connect(self.socket_path)
                    client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                    response = b""
                    while not response.endswith(b"\n"):
                        chunk = client.recv(8192)
                        if not chunk:
                            break
                        response += chunk
                    if response:
                        return json.loads(response.decode("utf-8").strip())
            except (OSError, socket.timeout, json.JSONDecodeError):
                GLib.usleep(70_000)
        return None

    def _wait_for_socket(self, timeout_ms=1200) -> bool:
        start = GLib.get_monotonic_time()
        timeout_us = timeout_ms * 1000
        while GLib.get_monotonic_time() - start < timeout_us:
            if os.path.exists(self.socket_path):
                return True
            GLib.usleep(50_000)
        return False

    def load_file(self, path: str):
        if not self._mpv_exists():
            raise RuntimeError("mpv is not installed or not in PATH")

        if self.process is None or self.process.poll() is not None:
            if os.path.exists(self.socket_path):
                try:
                    os.remove(self.socket_path)
                except OSError:
                    pass

            self.process = subprocess.Popen(
                [
                    "mpv",
                    "--idle=yes",
                    "--no-video",
                    "--force-window=no",
                    "--input-ipc-server=" + self.socket_path,
                    "--title=adria-music-player",
                    *([f"--script={self.mpris_script_path}"] if self.mpris_script_path else []),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if not self._wait_for_socket():
                raise RuntimeError("Failed to initialize mpv IPC socket")

        self._send_command(["loadfile", path, "replace"])

    def append_file(self, path: str):
        self._send_command(["loadfile", path, "append-play"])

    def toggle_play_pause(self):
        self._send_command(["cycle", "pause"])

    def set_paused(self, paused: bool):
        self._send_command(["set_property", "pause", paused])

    def stop(self):
        self._send_command(["stop"])

    def playlist_next(self):
        self._send_command(["playlist-next", "force"])

    def playlist_prev(self):
        self._send_command(["playlist-prev", "force"])

    def playlist_shuffle(self):
        self._send_command(["playlist-shuffle"])

    def playlist_move(self, from_index: int, to_index: int):
        self._send_command(["playlist-move", int(from_index), int(to_index)])

    def set_loop_playlist(self, enabled: bool):
        value = "inf" if enabled else "no"
        self._send_command(["set_property", "loop-playlist", value])

    def seek_absolute(self, seconds: float):
        self._send_command(["set_property", "time-pos", seconds])

    def get_time_pos(self) -> float:
        resp = self._send_command(["get_property", "time-pos"])
        return float(resp.get("data", 0.0)) if resp and "data" in resp else 0.0

    def get_duration(self) -> float:
        resp = self._send_command(["get_property", "duration"])
        return float(resp.get("data", 0.0)) if resp and "data" in resp else 0.0

    def get_playlist_pos(self) -> int:
        resp = self._send_command(["get_property", "playlist-pos"])
        if not resp or "data" not in resp:
            return -1
        try:
            return int(resp["data"])
        except (TypeError, ValueError):
            return -1

    def get_playlist_paths(self) -> list[str]:
        resp = self._send_command(["get_property", "playlist"])
        if not resp or "data" not in resp or not isinstance(resp["data"], list):
            return []

        items = []
        for entry in resp["data"]:
            if not isinstance(entry, dict):
                continue
            filename = entry.get("filename")
            if filename:
                items.append(str(filename))
        return items

    def get_current_path(self) -> str | None:
        resp = self._send_command(["get_property", "path"])
        if not resp or "data" not in resp:
            return None
        value = resp.get("data")
        return str(value) if value else None

    def close(self):
        if self.process and self.process.poll() is None:
            self._send_command(["quit"])
            try:
                self.process.terminate()
            except OSError:
                pass
        self.process = None
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass


class DownloadManager:
    """Runs yt-dlp downloads asynchronously without blocking GTK main loop."""

    YOUTUBE_DOMAINS = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "music.youtube.com",
    }
    SPOTIFY_DOMAINS = {
        "spotify.com",
        "www.spotify.com",
        "open.spotify.com",
    }

    def __init__(self):
        self._worker = None
        self._active = False

    def is_busy(self) -> bool:
        return self._active

    @staticmethod
    def check_dependencies() -> list[str]:
        missing = []
        for binary in ("yt-dlp", "ffmpeg"):
            if shutil.which(binary) is None:
                missing.append(binary)
        return missing

    @classmethod
    def detect_source(cls, url: str) -> str | None:
        parsed = urlparse(url.strip())
        host = parsed.netloc.lower()
        if host in cls.YOUTUBE_DOMAINS:
            return "youtube"
        if host in cls.SPOTIFY_DOMAINS:
            return "spotify"
        return None

    @staticmethod
    def _build_command(source: str, url: str, output_template: str) -> list[str]:
        base = [
            "yt-dlp",
            "--no-overwrites",
            "-x",
            "--audio-format",
            "mp3",
            "--embed-thumbnail",
            "--add-metadata",
            "-o",
            output_template,
        ]
        if source == "spotify":
            base.insert(1, "--yes-playlist")
        base.append(url)
        return base

    def start_download(
        self,
        source: str,
        url: str,
        destination: Path,
        on_progress,
        on_finished,
    ):
        if self._active:
            on_finished(False, "A download is already in progress.", [])
            return

        missing = self.check_dependencies()
        if missing:
            on_finished(False, f"Missing dependencies: {', '.join(missing)}", [])
            return

        expected = self.detect_source(url)
        if expected != source:
            on_finished(False, f"URL does not match {source}.", [])
            return

        destination.mkdir(parents=True, exist_ok=True)
        output_template = str(destination / "%(title)s.%(ext)s")
        command = self._build_command(source, url, output_template)
        try:
            existing_audio = {
                str(p.resolve())
                for p in destination.iterdir()
                if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
            }
        except OSError as exc:
            on_finished(False, f"Could not inspect the destination folder: {exc}", [])
            return

        self._active = True
        self._worker = threading.Thread(
            target=self._run_download,
            args=(command, destination, existing_audio, on_progress, on_finished),
            daemon=True,
        )
        self._worker.start()

    def _run_download(self, command: list[str], destination: Path, existing_audio: set[str], on_progress, on_finished):
        last_lines = []
        progress_re = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            self._active = False
            GLib.idle_add(on_finished, False, f"Could not run yt-dlp: {exc}", [])
            return

        for line in process.stdout or []:
            clean = line.strip()
            if not clean:
                continue
            last_lines.append(clean)
            if len(last_lines) > 12:
                last_lines.pop(0)

            match = progress_re.search(clean)
            if match:
                GLib.idle_add(on_progress, f"{match.group(1)}%")
            elif "[ExtractAudio]" in clean or "[Metadata]" in clean:
                GLib.idle_add(on_progress, clean)

        code = process.wait()
        self._active = False
        if code == 0:
            try:
                new_audio = sorted(
                    str(p.resolve())
                    for p in destination.iterdir()
                    if p.is_file()
                    and p.suffix.lower() in AUDIO_EXTENSIONS
                    and str(p.resolve()) not in existing_audio
                )
            except OSError as exc:
                GLib.idle_add(on_finished, False, f"Download finished, but the folder could not be refreshed: {exc}", [])
                return
            GLib.idle_add(on_finished, True, "Download completed.", new_audio)
            return

        error_text = "\n".join(last_lines[-4:]) if last_lines else "Unknown yt-dlp error."
        GLib.idle_add(on_finished, False, error_text, [])


class PlayerModel:
    """Pure app state + metadata extraction."""

    def __init__(self):
        self.state = TrackState()

    def load_folder_tracks(self, folderpath: str) -> list[str]:
        folder = Path(folderpath)
        self.state.folder_path = str(folder.resolve())
        tracks = sorted(
            str(p.resolve()) for p in folder.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
        )
        self.state.playlist = tracks
        if not tracks:
            self.clear_loaded_track()
        return tracks

    def clear_loaded_track(self):
        self.state.path = ""
        self.state.title = DEFAULT_TITLE
        self.state.artist = DEFAULT_ARTIST
        self.state.cover_data = None
        self.state.is_playing = False
        self.state.progress_fraction = 0.0

    def load_track_metadata(self, filepath: str):
        self.state.path = filepath
        self.state.title = Path(filepath).stem
        self.state.artist = DEFAULT_ARTIST
        self.state.cover_data = None

        try:
            meta = MutagenFile(filepath)
            if meta and meta.tags:
                if "TIT2" in meta.tags:
                    self.state.title = str(meta.tags.get("TIT2"))
                elif "title" in meta.tags:
                    raw = meta.tags.get("title")
                    self.state.title = raw[0] if isinstance(raw, list) and raw else str(raw)

                if "TPE1" in meta.tags:
                    self.state.artist = str(meta.tags.get("TPE1"))
                elif "artist" in meta.tags:
                    raw = meta.tags.get("artist")
                    self.state.artist = raw[0] if isinstance(raw, list) and raw else str(raw)

                if hasattr(meta.tags, "getall"):
                    apic = meta.tags.getall("APIC")
                    if apic:
                        self.state.cover_data = apic[0].data
                if not self.state.cover_data:
                    pictures = getattr(meta, "pictures", None)
                    if pictures:
                        self.state.cover_data = pictures[0].data
        except Exception:
            pass


class MusicPlayerView(Adw.ApplicationWindow):
    """GTK view only: creates widgets and renders state."""

    def __init__(self, app: Adw.Application):
        super().__init__(application=app)
        self._marquee_sources = {}

        self.set_title("Adria Music Player")
        self.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.set_size_request(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_name("adria-music-player-window")
        self.set_startup_id("adria-music-player")

        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.root.add_css_class("wal-root")

        self.download_youtube_button = Gtk.Button(icon_name="media-playback-start-symbolic")
        self.download_youtube_button.add_css_class("wal-btn")
        self.download_youtube_button.add_css_class("youtube-btn")
        self.download_youtube_button.set_tooltip_text("Download from YouTube")

        self.download_spotify_button = Gtk.Button(icon_name="audio-x-generic-symbolic")
        self.download_spotify_button.add_css_class("wal-btn")
        self.download_spotify_button.add_css_class("spotify-btn")
        self.download_spotify_button.set_tooltip_text("Download from Spotify")

        self.main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_row.add_css_class("main-row")
        self.main_row.set_spacing(14)
        self.main_row.set_valign(Gtk.Align.START)

        self.cover_stack = Gtk.Stack()
        self.cover_stack.add_css_class("cover-stack")
        self.cover_stack.set_valign(Gtk.Align.START)

        self.cover_box = Gtk.Box()
        self.cover_box.add_css_class("cover-frame")
        self.cover_picture = Gtk.Picture()
        self.cover_picture.set_content_fit(Gtk.ContentFit.COVER)
        self.cover_picture.set_can_shrink(True)
        self.cover_picture.add_css_class("cover-picture")
        self.cover_box.append(self.cover_picture)

        self.placeholder = Gtk.Label(label="♪")
        self.placeholder.add_css_class("placeholder")

        self.cover_stack.add_named(self.cover_box, "cover")
        self.cover_stack.add_named(self.placeholder, "placeholder")
        self.cover_stack.set_visible_child_name("placeholder")

        self.info_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.info_col.add_css_class("info-col")
        self.info_col.set_spacing(8)
        self.info_col.set_valign(Gtk.Align.START)

        self.header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.header_row.add_css_class("header-row")
        self.header_row.set_spacing(8)

        self.text_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.text_col.add_css_class("text-col")
        self.text_col.set_hexpand(True)
        self.text_col.set_valign(Gtk.Align.START)

        self.download_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.download_buttons_box.add_css_class("download-buttons-box")
        self.download_buttons_box.set_spacing(4)
        self.download_buttons_box.set_valign(Gtk.Align.START)

        self.title_label = Gtk.Label(label="No file loaded")
        self.title_label.set_xalign(0)
        self.title_label.set_single_line_mode(True)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_max_width_chars(TEXT_VIEW_CHARS)
        self.title_label.add_css_class("title")

        self.artist_label = Gtk.Label(label="Unknown artist")
        self.artist_label.set_xalign(0)
        self.artist_label.set_single_line_mode(True)
        self.artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.artist_label.set_max_width_chars(TEXT_VIEW_CHARS)
        self.artist_label.add_css_class("artist")

        self.controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.controls.add_css_class("controls")
        self.controls.set_spacing(12)

        self.btn_load = Gtk.Button(icon_name="folder-open-symbolic")
        self.btn_load.add_css_class("wal-btn")
        self.btn_load.set_tooltip_text("Select music folder")

        self.btn_play_pause = Gtk.Button(icon_name="media-playback-start-symbolic")
        self.btn_play_pause.add_css_class("wal-btn")
        self.btn_play_pause.add_css_class("play-btn")

        self.btn_prev = Gtk.Button(icon_name="media-skip-backward-symbolic")
        self.btn_prev.add_css_class("wal-btn")

        self.btn_next = Gtk.Button(icon_name="media-skip-forward-symbolic")
        self.btn_next.add_css_class("wal-btn")

        self.btn_stop = Gtk.Button(icon_name="media-playback-stop-symbolic")
        self.btn_stop.add_css_class("wal-btn")

        self.btn_shuffle = Gtk.ToggleButton(icon_name="media-playlist-shuffle-symbolic")
        self.btn_shuffle.add_css_class("wal-btn")
        self.btn_shuffle.add_css_class("shuffle-btn")
        self.btn_shuffle.set_tooltip_text("Shuffle playlist")

        self.controls.append(self.btn_load)
        self.controls.append(self.btn_prev)
        self.controls.append(self.btn_play_pause)
        self.controls.append(self.btn_next)
        self.controls.append(self.btn_stop)
        self.controls.append(self.btn_shuffle)

        self.text_col.append(self.title_label)
        self.text_col.append(self.artist_label)

        self.download_buttons_box.append(self.download_youtube_button)
        self.download_buttons_box.append(self.download_spotify_button)

        self.header_row.append(self.text_col)
        self.header_row.append(self.download_buttons_box)

        self.info_col.append(self.header_row)
        self.info_col.append(self.controls)

        self.main_row.append(self.cover_stack)
        self.main_row.append(self.info_col)

        self.progress = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01)
        self.progress.set_draw_value(False)
        self.progress.add_css_class("wal-progress")
        self.progress.set_hexpand(True)

        self.root.append(self.main_row)
        self.root.append(self.progress)

        drag = Gtk.GestureClick.new()
        self.root.add_controller(drag)
        self.drag_gesture = drag

        seek_gesture = Gtk.GestureClick.new()
        self.progress.add_controller(seek_gesture)
        self.seek_gesture = seek_gesture

        self.set_content(self.root)

    def update_track_info(self, title: str, artist: str):
        self._set_marquee_text("title", self.title_label, title)
        self._set_marquee_text("artist", self.artist_label, artist)

    def update_play_state(self, is_playing: bool):
        if is_playing:
            self.btn_play_pause.set_icon_name("media-playback-pause-symbolic")
        else:
            self.btn_play_pause.set_icon_name("media-playback-start-symbolic")

    def update_progress(self, fraction: float):
        self.progress.set_value(max(0.0, min(1.0, fraction)))

    def update_cover(self, image_data: bytes | None):
        if not image_data:
            self.cover_stack.set_visible_child_name("placeholder")
            return

        loader = GdkPixbuf.PixbufLoader()
        try:
            loader.write(image_data)
            loader.close()
            pixbuf = loader.get_pixbuf()
            if pixbuf is None:
                self.cover_stack.set_visible_child_name("placeholder")
                return

            width = pixbuf.get_width()
            height = pixbuf.get_height()
            side = min(width, height)
            offset_x = (width - side) // 2
            offset_y = (height - side) // 2
            square = pixbuf.new_subpixbuf(offset_x, offset_y, side, side)
            scaled = square.scale_simple(COVER_SIZE, COVER_SIZE, GdkPixbuf.InterpType.BILINEAR)
            if scaled is None:
                self.cover_stack.set_visible_child_name("placeholder")
                return

            texture = Gdk.Texture.new_for_pixbuf(scaled)
            self.cover_picture.set_paintable(texture)
            self.cover_stack.set_visible_child_name("cover")
        except GLib.Error:
            self.cover_stack.set_visible_child_name("placeholder")

    def show_error(self, message: str):
        dialog = Adw.MessageDialog.new(self, "Error", message)
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present()

    def create_download_dialog(self, source: str) -> dict:
        title = "Download from YouTube" if source == "youtube" else "Download from Spotify"
        dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dialog.add_css_class("download-dialog")
        cancel_button = dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        cancel_button.add_css_class("download-action-btn")
        cancel_button.add_css_class("download-cancel-btn")
        download_button = dialog.add_button("Download", Gtk.ResponseType.OK)
        download_button.add_css_class("download-action-btn")
        download_button.add_css_class("download-confirm-btn-yt" if source == "youtube" else "download-confirm-btn-spotify")
        download_button.add_css_class("suggested-action")
        dialog.set_default_response(Gtk.ResponseType.OK)

        content = dialog.get_content_area()
        content.add_css_class("download-dialog-content")
        content.set_spacing(8)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("download-dialog-title")
        title_label.set_xalign(0.0)

        url_entry = Gtk.Entry()
        url_entry.add_css_class("download-url-entry")
        url_entry.set_placeholder_text("Paste URL")
        url_entry.set_activates_default(True)

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_row.add_css_class("download-status-row")
        status_row.set_visible(False)
        spinner = Gtk.Spinner()
        spinner.set_visible(False)
        status_label = Gtk.Label(label="")
        status_label.set_xalign(0.0)
        status_label.set_hexpand(True)
        status_label.set_ellipsize(Pango.EllipsizeMode.END)
        status_row.append(spinner)
        status_row.append(status_label)

        content.append(title_label)
        content.append(url_entry)
        content.append(status_row)

        return {
            "dialog": dialog,
            "url_entry": url_entry,
            "download_button": download_button,
            "cancel_button": cancel_button,
            "spinner": spinner,
            "status_label": status_label,
            "status_row": status_row,
        }

    def _stop_marquee(self, key: str):
        source_id = self._marquee_sources.pop(key, None)
        if source_id is not None:
            GLib.source_remove(source_id)

    def _set_marquee_text(self, key: str, label: Gtk.Label, text: str):
        self._stop_marquee(key)
        text = (text or "").strip() or "-"
        label.set_text(text)
        if len(text) <= TEXT_VIEW_CHARS:
            return

        spacer = "      "
        scroll_base = text + spacer
        stream = scroll_base + scroll_base
        state = {"offset": 0}

        def tick():
            offset = state["offset"]
            window = stream[offset : offset + TEXT_VIEW_CHARS]
            label.set_text(window)

            state["offset"] = (offset + 1) % len(scroll_base)
            return True

        self._marquee_sources[key] = GLib.timeout_add(MARQUEE_TICK_MS, tick)


class MusicPlayerController:
    """Orchestrates model/view/mpv and user interactions."""

    def __init__(self, model: PlayerModel, view: MusicPlayerView, mpv: MPVController, theme_manager: WalThemeManager):
        self.model = model
        self.view = view
        self.mpv = mpv
        self.theme_manager = theme_manager
        self.download_manager = DownloadManager()
        self.is_user_seeking = False
        self.last_seek_interaction_us = 0
        self.current_index = -1
        self.base_playlist_order: list[str] = []

        self.view.btn_load.connect("clicked", self._on_load_clicked)
        self.view.btn_prev.connect("clicked", self._on_prev_clicked)
        self.view.btn_play_pause.connect("clicked", self._on_play_pause_clicked)
        self.view.btn_next.connect("clicked", self._on_next_clicked)
        self.view.btn_stop.connect("clicked", self._on_stop_clicked)
        self.view.btn_shuffle.connect("toggled", self._on_shuffle_toggled)
        self.view.download_youtube_button.connect("clicked", self._on_download_youtube_clicked)
        self.view.download_spotify_button.connect("clicked", self._on_download_spotify_clicked)
        self.view.progress.connect("value-changed", self._on_progress_changed)

        self.view.drag_gesture.connect("pressed", self._on_drag_pressed)
        self.view.seek_gesture.connect("pressed", self._on_seek_pressed)
        self.view.seek_gesture.connect("released", self._on_seek_released)
        self.view.seek_gesture.connect("cancel", self._on_seek_cancelled)
        self.view.connect("close-request", self._on_close_request)

        GLib.timeout_add(200, self._poll_progress)

    def _on_drag_pressed(self, gesture, _n_press, x, y):
        event = gesture.get_current_event()
        device = gesture.get_current_event_device()
        if event is None or device is None:
            return
        try:
            self.view.begin_move_drag(device, 1, int(x), int(y), event.get_time())
        except Exception:
            pass

    def _on_load_clicked(self, _button):
        dialog = Gtk.FileDialog(title="Select music folder")
        dialog.select_folder(self.view, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return

        if not folder:
            return

        folderpath = folder.get_path()
        if not folderpath:
            return

        try:
            tracks = self.model.load_folder_tracks(folderpath)
        except OSError as err:
            self.model.clear_loaded_track()
            self._apply_track_visuals()
            self.view.update_play_state(False)
            self.view.update_progress(0.0)
            self.view.show_error(f"Could not read the selected folder:\n{err}")
            return

        if not tracks:
            self.current_index = -1
            self.base_playlist_order = []
            self.model.clear_loaded_track()
            self._apply_track_visuals()
            self.view.update_play_state(False)
            self.view.update_progress(0.0)
            self.view.show_error("The selected folder does not contain supported audio files.")
            return

        first_track = tracks[0]
        self.current_index = 0
        self.base_playlist_order = list(tracks)
        self.view.btn_shuffle.set_active(False)
        self.model.load_track_metadata(first_track)
        self._apply_track_visuals()

        try:
            self.mpv.load_file(first_track)
            for extra_track in tracks[1:]:
                self.mpv.append_file(extra_track)
            self.mpv.set_loop_playlist(True)
            self.mpv.set_paused(True)
            self.model.state.is_playing = False
            self.view.update_play_state(False)
        except RuntimeError as err:
            self.model.state.is_playing = False
            self.view.update_play_state(False)
            self.view.show_error(str(err))

    def _set_current_track_from_index(self):
        if not self.model.state.playlist:
            return
        if self.current_index < 0 or self.current_index >= len(self.model.state.playlist):
            return
        current = self.model.state.playlist[self.current_index]
        self.model.load_track_metadata(current)
        self._apply_track_visuals()

    def _apply_track_visuals(self):
        self.view.update_track_info(self.model.state.title, self.model.state.artist)
        self.view.update_cover(self.model.state.cover_data)
        self.theme_manager.set_cover_theme(self.model.state.cover_data)

    def _sync_current_track_from_mpv(self):
        current_path = self.mpv.get_current_path()
        if not current_path:
            return
        current_path = str(Path(current_path).resolve())
        if not self.model.state.playlist:
            return
        try:
            new_index = next(
                i for i, p in enumerate(self.model.state.playlist) if str(Path(p).resolve()) == current_path
            )
        except StopIteration:
            return

        if new_index != self.current_index or self.model.state.path != self.model.state.playlist[new_index]:
            self.current_index = new_index
            self._set_current_track_from_index()

    def _on_prev_clicked(self, _button):
        if not self.model.state.playlist:
            return

        current_pos = self.mpv.get_time_pos()
        if current_pos > 5.0:
            self.mpv.seek_absolute(0.0)
            return

        self.mpv.playlist_prev()
        self.current_index = (self.current_index - 1) % len(self.model.state.playlist)
        self._set_current_track_from_index()

    def _on_next_clicked(self, _button):
        if not self.model.state.playlist:
            return
        self.mpv.playlist_next()
        self.current_index = (self.current_index + 1) % len(self.model.state.playlist)
        self._set_current_track_from_index()

    def _on_play_pause_clicked(self, _button):
        if not self.model.state.playlist:
            self.view.show_error("Load a music folder before trying to play audio.")
            return
        self.mpv.toggle_play_pause()
        self.model.state.is_playing = not self.model.state.is_playing
        self.view.update_play_state(self.model.state.is_playing)

    def _on_stop_clicked(self, _button):
        self.mpv.stop()
        self.model.state.is_playing = False
        self.model.state.progress_fraction = 0.0
        self.view.update_play_state(False)
        self.view.update_progress(0.0)

    def _on_shuffle_toggled(self, button):
        if not button.get_active():
            if (
                len(self.base_playlist_order) == len(self.model.state.playlist)
                and len(self.base_playlist_order) > 1
            ):
                self._reorder_playlist(self.base_playlist_order)
            return
        if len(self.model.state.playlist) < 2:
            button.set_active(False)
            return
        current_pos = self.mpv.get_playlist_pos()
        if current_pos < 0:
            current_pos = self.current_index
        if current_pos < 0 or current_pos >= len(self.model.state.playlist):
            current_pos = 0

        playlist = list(self.model.state.playlist)
        size = len(playlist)
        cycle_slots = list(range(current_pos + 1, size)) + list(range(0, current_pos))
        if not cycle_slots:
            return

        shuffled_upcoming = [playlist[i] for i in cycle_slots]
        random.shuffle(shuffled_upcoming)

        desired_order = list(playlist)
        for slot, track in zip(cycle_slots, shuffled_upcoming):
            desired_order[slot] = track

        self._reorder_playlist(desired_order)
        self.current_index = current_pos

    def _reorder_playlist(self, desired_order: list[str]):
        if not desired_order or len(desired_order) != len(self.model.state.playlist):
            return

        current_mpv = self.mpv.get_playlist_paths()
        if len(current_mpv) != len(desired_order):
            current_mpv = list(self.model.state.playlist)

        working = list(current_mpv)
        for target_idx, wanted in enumerate(desired_order):
            try:
                source_idx = working.index(wanted, target_idx)
            except ValueError:
                continue
            if source_idx == target_idx:
                continue
            self.mpv.playlist_move(source_idx, target_idx)
            moved = working.pop(source_idx)
            working.insert(target_idx, moved)

        self.model.state.playlist = list(desired_order)

        current_path = self.mpv.get_current_path()
        if not current_path:
            return
        current_path = str(Path(current_path).resolve())
        try:
            self.current_index = next(
                i
                for i, p in enumerate(self.model.state.playlist)
                if str(Path(p).resolve()) == current_path
            )
        except StopIteration:
            pass

    def _on_download_youtube_clicked(self, _button):
        self._open_download_dialog("youtube")

    def _on_download_spotify_clicked(self, _button):
        self._open_download_dialog("spotify")

    def _resolve_download_folder(self) -> Path | None:
        if self.model.state.folder_path:
            return Path(self.model.state.folder_path)
        if not self.model.state.path:
            return None
        return Path(self.model.state.path).parent

    def _open_download_dialog(self, source: str):
        destination = self._resolve_download_folder()
        if destination is None:
            self.view.show_error("Load a folder first to define the download destination.")
            return

        parts = self.view.create_download_dialog(source)
        dialog = parts["dialog"]
        dialog.connect("response", self._on_download_dialog_response, source, destination, parts)
        dialog.present()

    def _on_download_dialog_response(self, dialog, response_id, source: str, destination: Path, parts: dict):
        if response_id != Gtk.ResponseType.OK:
            dialog.close()
            return

        url = parts["url_entry"].get_text().strip()
        if not url:
            parts["status_label"].set_text("Paste a valid URL.")
            return

        parts["download_button"].set_sensitive(False)
        parts["cancel_button"].set_sensitive(False)
        parts["status_row"].set_visible(True)
        parts["spinner"].set_visible(True)
        parts["spinner"].start()
        parts["status_label"].set_text("Downloading...")

        self.download_manager.start_download(
            source=source,
            url=url,
            destination=destination,
            on_progress=lambda text: self._on_download_progress(parts, text),
            on_finished=lambda ok, message, files: self._on_download_finished(parts, dialog, ok, message, files),
        )

    def _on_download_progress(self, parts: dict, text: str):
        parts["status_label"].set_text(text)
        return False

    def _on_download_finished(self, parts: dict, dialog: Gtk.Dialog, ok: bool, message: str, files: list[str]):
        parts["spinner"].stop()
        parts["spinner"].set_visible(False)
        parts["download_button"].set_sensitive(True)
        parts["cancel_button"].set_sensitive(True)
        dialog.close()
        if ok and files:
            for filepath in files:
                if filepath not in self.model.state.playlist:
                    self.model.state.playlist.append(filepath)
                    if filepath not in self.base_playlist_order:
                        self.base_playlist_order.append(filepath)
                    self.mpv.append_file(filepath)
        if ok:
            dialog = Adw.MessageDialog.new(self.view, "Download complete", message)
        else:
            dialog = Adw.MessageDialog.new(self.view, "Download error", message)
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present()
        return False

    def _on_seek_pressed(self, *_args):
        self.is_user_seeking = True
        self.last_seek_interaction_us = GLib.get_monotonic_time()

    def _on_seek_released(self, *_args):
        self.is_user_seeking = False
        self._apply_seek_from_view()

    def _on_seek_cancelled(self, *_args):
        self.is_user_seeking = False

    def _on_progress_changed(self, _scale):
        if self.is_user_seeking:
            self.last_seek_interaction_us = GLib.get_monotonic_time()
            self._apply_seek_from_view()

    def _apply_seek_from_view(self):
        duration = self.mpv.get_duration()
        if duration <= 0:
            return
        target = self.view.progress.get_value() * duration
        self.mpv.seek_absolute(target)

    def _poll_progress(self):
        if self.is_user_seeking:
            # Safety fallback: if release event is missed, recover automatic updates.
            now = GLib.get_monotonic_time()
            if now - self.last_seek_interaction_us > 900_000:
                self.is_user_seeking = False

        if self.is_user_seeking:
            return True

        self._sync_current_track_from_mpv()
        playlist_pos = self.mpv.get_playlist_pos()
        if playlist_pos >= 0 and playlist_pos != self.current_index:
            self.current_index = playlist_pos
            self._set_current_track_from_index()

        duration = self.mpv.get_duration()
        current = self.mpv.get_time_pos()
        if duration > 0:
            fraction = max(0.0, min(1.0, current / duration))
            self.model.state.progress_fraction = fraction
            self.view.update_progress(fraction)

        return True

    def _on_close_request(self, *_args):
        self.mpv.close()
        return False


class WalPlayerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.theme_manager = None
        self.controller = None

    def do_activate(self):
        self.theme_manager = WalThemeManager()

        win = self.props.active_window
        if win is None:
            model = PlayerModel()
            view = MusicPlayerView(self)
            mpv = MPVController()
            self.controller = MusicPlayerController(model, view, mpv, self.theme_manager)
            win = view

        win.present()


def main():
    GLib.set_prgname("adria-music-player")
    app = WalPlayerApp()
    return app.run(None)


if __name__ == "__main__":
    raise SystemExit(main())
