# Maintainer: Adria
pkgname=adria-music-player
pkgver=0.1.0
pkgrel=1
pkgdesc='Minimal GTK4/libadwaita floating music player with mpv + wal theme sync'
arch=('any')
url='https://github.com/adria/adria-music-player'
license=('MIT')
depends=(
  'python'
  'python-gobject'
  'gtk4'
  'libadwaita'
  'mpv'
  'python-mutagen'
  'yt-dlp'
  'ffmpeg'
  'mpv-mpris'
)
source=(
  'adria_music_player.py'
  'adria_music_player.css'
  'adria-music-player.desktop'
  'README.md'
)
sha256sums=('SKIP' 'SKIP' 'SKIP' 'SKIP')

package() {
  install -Dm755 "${srcdir}/adria_music_player.py" "${pkgdir}/usr/lib/adria-music-player/adria_music_player.py"
  install -Dm644 "${srcdir}/adria_music_player.css" "${pkgdir}/usr/lib/adria-music-player/adria_music_player.css"

  install -Dm644 "${srcdir}/README.md" "${pkgdir}/usr/share/doc/adria-music-player/README.md"
  install -Dm644 "${srcdir}/adria-music-player.desktop" "${pkgdir}/usr/share/applications/adria-music-player.desktop"

  install -Dm755 /dev/stdin "${pkgdir}/usr/bin/adria-music-player" <<'SH'
#!/usr/bin/env sh
exec python /usr/lib/adria-music-player/adria_music_player.py "$@"
SH
}
