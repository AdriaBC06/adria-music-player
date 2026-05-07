# Maintainer: Adria
pkgname=adria-music-player
pkgver=0.1.0
pkgrel=1
pkgdesc='Minimal GTK4/libadwaita music player for Linux powered by mpv'
arch=('any')
url='https://github.com/AdriaBC06/adria-music-player'
license=('MIT')
depends=(
  'python'
  'python-gobject'
  'gtk4'
  'libadwaita'
  'mpv'
  'python-mutagen'
)
optdepends=(
  'yt-dlp: download audio from supported URLs'
  'ffmpeg: audio extraction and conversion for yt-dlp downloads'
  'mpv-mpris: MPRIS integration for Waybar and desktop media controls'
)
source=(
  'adria_music_player.py'
  'adria_music_player.css'
  'adria-music-player.desktop'
  'LICENSE'
  'README.md'
)
sha256sums=('SKIP' 'SKIP' 'SKIP' 'SKIP' 'SKIP')

package() {
  install -Dm755 "${srcdir}/adria_music_player.py" "${pkgdir}/usr/lib/adria-music-player/adria_music_player.py"
  install -Dm644 "${srcdir}/adria_music_player.css" "${pkgdir}/usr/lib/adria-music-player/adria_music_player.css"

  install -Dm644 "${srcdir}/README.md" "${pkgdir}/usr/share/doc/adria-music-player/README.md"
  install -Dm644 "${srcdir}/LICENSE" "${pkgdir}/usr/share/licenses/adria-music-player/LICENSE"
  install -Dm644 "${srcdir}/adria-music-player.desktop" "${pkgdir}/usr/share/applications/adria-music-player.desktop"

  install -Dm755 /dev/stdin "${pkgdir}/usr/bin/adria-music-player" <<'SH'
#!/usr/bin/env sh
exec /usr/bin/python /usr/lib/adria-music-player/adria_music_player.py "$@"
SH
}
