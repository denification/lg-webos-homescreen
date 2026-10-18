#!/bin/sh
# home-overlay.sh — Overlay-mount for the stock LG home app (com.webos.app.home).
#
# Instead of cp + bind-mount, this uses the kernel overlay filesystem:
# lowerdir = original assets (read-only), upperdir = only the changed files.
# No /tmp copy, mounts in ~0.1s, low memory.
# Method: mareklarek/webos10-homescreen-customization issue #2 (ArnoldDeRuiter),
# measured on webOS 10.3.1. Revert = umount (a reboot also clears it).
#
# Sources from: tld.my.customhome/assets/ (home*.xml patches + images/)
# i18n: clean copy as base, with "Go to Apps" / headline emptied.
set -e

ASSETS_DIR=/usr/palm/applications/com.webos.app.home/data/flutter_assets/assets
OVERRIDE_DIR=/media/developer/apps/usr/palm/applications/tld.my.customhome/assets
# UPPER/WORK live on the persistent flash partition: /tmp is wiped on reboot,
# which previously made the mod disappear after every restart.
CUSTOMHOME=/media/developer/apps/usr/palm/applications/tld.my.customhome
UPPER=$CUSTOMHOME/overlay-upper
WORK=$CUSTOMHOME/overlay-work
CLEAN_I18N=/var/lib/webosbrew/launcher-clean/i18n-full

if [ -f "$OVERRIDE_DIR/DISABLED" ]; then
  echo "DISABLED flag present — removing overlay"
  umount "$ASSETS_DIR" 2>/dev/null || true
  pkill -f '[c]om.webos.app.home' 2>/dev/null || true
  exit 0
fi

umount "$ASSETS_DIR" 2>/dev/null || true
mkdir -p "$UPPER" "$WORK"
rm -rf "$UPPER/images" "$UPPER/i18n"
mkdir -p "$UPPER/images/4k" "$UPPER/images/2k" "$UPPER/images/hd" "$UPPER/i18n"

# Layout XML overrides (shadowed into upper)
for f in home.xml home_lg.xml home_wee.xml home_senior.xml home_layoutShelfView.xml; do
  [ -f "$OVERRIDE_DIR/$f" ] && cp "$OVERRIDE_DIR/$f" "$UPPER/$f"
done

# Wallpaper overrides
for sub in 4k 2k hd; do
  [ -f "$OVERRIDE_DIR/images/$sub/bg_banner_img.png" ] && \
    cp "$OVERRIDE_DIR/images/$sub/bg_banner_img.png" "$UPPER/images/$sub/"
done

# i18n: clean copy (shadows the real dir behind the symlink in upper —
# confirmed by ArnoldDeRuiter). Falls back to copying through the symlink.
if [ -d "$CLEAN_I18N" ]; then
  cp -R "$CLEAN_I18N/." "$UPPER/i18n/"
else
  rm -rf "$UPPER/i18n"
  cp -R --no-dereference "$ASSETS_DIR/i18n/." "$UPPER/i18n/" 2>/dev/null || true
fi
# Empty "Go to Apps" + headline (all locales; BusyBox has no sed -i -> tmp+mv)
for j in "$UPPER"/i18n/*.json; do
  [ -f "$j" ] || continue
  sed 's/"Go to Apps": "[^"]*"/"Go to Apps": ""/; s/"Start a new experience with webOS\.": "[^"]*"/"Start a new experience with webOS.": ""/' "$j" > "$j.tmp" && mv "$j.tmp" "$j"
done

mount -t overlay overlay -o "lowerdir=$ASSETS_DIR,upperdir=$UPPER,workdir=$WORK" "$ASSETS_DIR"
pkill -f '[c]om.webos.app.home' 2>/dev/null || true
echo "home overlay applied (mount -t overlay)"
