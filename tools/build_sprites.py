#!/usr/bin/env python3
# build_sprites.py — Build the RGBA sprite atlases on a Mac (Pillow required).
# The TV has no PIL, so glyph rendering happens here; the TV only pastes
# pre-rendered pixels. Outputs: assets/sprites/<name>.raw + .json
#
# Usage:  python3 tools/build_sprites.py
#
# Font: Conthrax SemiBold (Typodermic, free for commercial use under the
# Typodermic Desktop License). Drop the .ttf/.otf next to this script or
# point FONT_PATH at it. Change the sizes/colors below to retune the layout.
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT_PATH = os.environ.get(
    'FONT_PATH',
    os.path.join(HERE, 'conthrax-sb.ttf'),
)
OUT = os.path.join(ROOT, 'assets', 'sprites')

# name -> (font size px, RGB color). Keep these in sync with bg-generator.py.
SPRITES = {
    'clock': (208, (125, 211, 252)),   # #7dd3fc clock (guide 6.4)
    'date':  (72,  (192, 216, 232)),   # #c0d8e8 weekday/date (guide 6.5)
    'big':   (224, (168, 213, 242)),   # #a8d5f2 temperature
    'small': (96,  (168, 213, 242)),   # #a8d5f2 condition
}

CHARS = (
    '0123456789:°%+-./ '
    'ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ'
    'abcçdefgğhıijklmnoöprsştuüvyz'
)


def build(name, size, color):
    font = ImageFont.truetype(FONT_PATH, size)
    atlas_h = int(size * 1.6)
    entries, x = [], 0
    for ch in CHARS:
        bbox = font.getbbox(ch)
        if bbox is None:
            continue
        w = bbox[2] - bbox[0] + 8
        entries.append((ch, w, bbox))
        x += w
    atlas_w = x + 16
    img = Image.new('RGBA', (atlas_w, atlas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    mc, x = {}, 8
    asc, _ = font.getmetrics()
    for ch, w, bbox in entries:
        y0 = asc - bbox[3]            # baseline-align every glyph
        d.text((x - bbox[0], y0), ch, font=font, fill=color + (255,))
        mc[ch] = [x - bbox[0], y0 + bbox[1], bbox[2] - bbox[0] + 4, bbox[3] - bbox[1] + 2]
        x += w
    with open(os.path.join(OUT, name + '.raw'), 'wb') as f:
        f.write(img.tobytes())
    with open(os.path.join(OUT, name + '.json'), 'w') as f:
        json.dump({'w': atlas_w, 'h': atlas_h, 'chars': mc}, f)
    print('%s %dpx -> atlas %dx%d, %d glyphs' % (name, size, atlas_w, atlas_h, len(mc)))


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for n, (sz, col) in SPRITES.items():
        build(n, sz, col)
