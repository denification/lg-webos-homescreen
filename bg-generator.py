#!/usr/bin/env python3
# bg-generator.py — Renders the stock LG home hero-banner wallpaper:
# Earth "Blue Marble" background + clock/date (top-left, Conthrax font,
# style adapted from section 6.4-6.5 of the webOS 9.2.2 QML customization
# guide by mareklarek) + weather (top-right, Open-Meteo).
#
# Design values taken from that guide (MainView_M.qml):
#   clock   : #7dd3fc, top-left; hours and minutes rendered as separate
#             glyphs so the blinking colon never shifts the digits (PNG is
#             static, so the colon does not blink here)
#   date    : #c0d8e8, Turkish day/month names as manual arrays (the QML
#             build had no locale strings; same approach here)
#   weather : #a8d5f2, top-right
#
# The TV has no PIL: PNG encoding is pure Python (zlib + chunks).
# Font glyphs are pre-rendered on a Mac into RGBA sprite atlases
# (tools/build_sprites.py) and shipped as .raw + .json.
#
# Loop: re-renders when the minute changes or the weather changes,
# writing three resolutions (4k/2k/hd share the same file).
#
# LIMIT: while the home app is open, Flutter caches the asset in memory;
# a re-render only becomes visible after the home app restarts. Render
# while home is CLOSED, then open home.
import os, sys, json, time, zlib, struct
import urllib.request

W, H = 3840, 1679
BASE = '/media/developer/apps/usr/palm/applications/tld.my.customhome/assets'
OUT_DIR = '/media/developer/apps/usr/palm/applications/tld.my.customhome/overlay-upper/images'  # overlay upperdir (persistent — /tmp is wiped on reboot)
LOG = '/tmp/bg-generator.log'

LAT, LON = 51.5074, -0.1278   # London (match TV weather setting)
TZ_OFFSET = 3 * 3600          # fixed GMT+3; the TV clock runs in GMT

# Display language (shown on the TV screen). Edit for your own language.
DAYS = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
          'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']

WMO = {0: 'Açık', 1: 'Çoğunlukla açık', 2: 'Parçalı bulutlu', 3: 'Kapalı',
       45: 'Sisli', 48: 'Sisli', 51: 'Çisenti', 53: 'Çisenti', 55: 'Çisenti',
       56: 'Donan çisenti', 57: 'Donan çisenti', 61: 'Yağmurlu', 63: 'Yağmurlu',
       65: 'Kuvvetli yağmur', 66: 'Donan yağmur', 67: 'Donan yağmur',
       71: 'Karlı', 73: 'Karlı', 75: 'Yoğun kar', 77: 'Kar taneleri',
       80: 'Sağanak', 81: 'Sağanak', 82: 'Kuvvetli sağanak',
       85: 'Kar sağanağı', 86: 'Kar sağanağı', 95: 'Gök gürültülü',
       96: 'Gök gürültülü dolu', 99: 'Gök gürültülü dolu'}

SPRITES = {}

def log(msg):
    with open(LOG, 'a') as f:
        f.write('[%d] %s\n' % (int(time.time() * 1000), msg))

def load_sprites():
    global SPRITES
    for name in ('big', 'small', 'clock', 'date'):
        with open('%s/sprites/%s.json' % (BASE, name)) as f:
            meta = json.load(f)
        with open('%s/sprites/%s.raw' % (BASE, name), 'rb') as f:
            raw = f.read()
        SPRITES[name] = (meta, raw)

def make_background():
    """Loads the background produced on a Mac: assets/images/bg_4k.raw
    (RGB, W*H*3 bytes) — the Earth 'Blue Marble' image, top-cropped to
    3840x1679 to match the hero banner's logical height."""
    raw = open(BASE + '/images/bg_4k.raw', 'rb').read()
    stride = W * 3
    rows = []
    for y in range(H):
        rows.append(bytearray(raw[y * stride:(y + 1) * stride]))
    return rows

def paste(buf, sprite, ch, x0, y0):
    """Pastes glyph ch at (x0, y0). Pixels with alpha >= 128 are copied."""
    meta, raw = sprite
    if ch not in meta['chars']:
        return
    sx, sy, w, h = meta['chars'][ch]
    sw = meta['w']
    for yy in range(h):
        ty = y0 + yy
        if ty < 0 or ty >= H:
            continue
        src_row = (sy + yy) * sw + sx
        row = buf[ty]
        for xx in range(w):
            so = (src_row + xx) * 4
            a = raw[so + 3]
            if a >= 128:
                # row is already buf[ty] — do NOT add ty*3 (that was the
                # skew/italic bug: every line shifted 1px to the right)
                do = (x0 + xx) * 3
                if 0 <= x0 + xx < W and do + 2 < W * 3:
                    row[do] = raw[so]
                    row[do + 1] = raw[so + 1]
                    row[do + 2] = raw[so + 2]

def draw_text(buf, sprite, text, x, y):
    meta, raw = sprite
    cx = x
    for ch in text:
        if ch in meta['chars']:
            sx, sy, w, h = meta['chars'][ch]
            paste(buf, sprite, ch, cx, y)
            cx += w + 6
        else:
            cx += 40
    return cx - x

def text_width(sprite, text):
    meta, _ = sprite
    w = 0
    for ch in text:
        if ch in meta['chars']:
            w += meta['chars'][ch][2] + 6
    return w

def fetch_weather_once():
    url = ('https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s'
           '&current=temperature_2m,weather_code&timezone=Europe/London'
           % (LAT, LON))
    req = urllib.request.Request(url, headers={'User-Agent': 'lg-webos-homescreen'})
    d = json.load(urllib.request.urlopen(req, timeout=10))
    cur = d.get('current', {})
    code = cur.get('weather_code', 3)
    return {
        'temp': int(round(cur.get('temperature_2m', 0))),
        'desc': WMO.get(code, 'Kapalı'),
    }

def fetch_weather():
    for attempt in range(4):
        try:
            return fetch_weather_once()
        except Exception as e:
            log('weather attempt %d: %r' % (attempt + 1, e))
            time.sleep(20 * (attempt + 1))
    log('weather unavailable — continuing with clock only')
    return {'temp': None, 'desc': None}

def png_encode(rgb_rows):
    """RGB row list -> PNG bytes (filter 0, zlib)."""
    raw = b''.join(b'\x00' + bytes(r) for r in rgb_rows)
    comp = zlib.compress(raw, 6)
    def chunk(typ, data):
        c = struct.pack('>I', len(data)) + typ + data
        return c + struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', comp) + chunk(b'IEND', b''))

def build(bg_rows, weather, now=None, test_mark=False):
    buf = [bytearray(r) for r in bg_rows]   # copy
    if now is None:
        now = time.gmtime(time.time() + TZ_OFFSET)

    # Sizes (shrunk 20% from the first iteration) + offsets
    CLOCK_SZ, DATE_SZ = 208, 72
    BIG_SZ, SMALL_SZ = 224, 96
    MARGIN = 150 + 384 - 154      # top-right margin: 10% left + 4% right = 380
    LEFT = 115                    # clock block: 3% right

    # --- Top-left: 3 lines — CLOCK / WEEKDAY / DATE (2-digit year) ---
    clock = '%02d:%02d' % (now.tm_hour, now.tm_min)
    draw_text(buf, SPRITES['clock'], clock, LEFT, 110)
    draw_text(buf, SPRITES['date'], DAYS[now.tm_wday], LEFT, 110 + CLOCK_SZ + 36)
    datestr = '%d %s %02d' % (now.tm_mday, MONTHS[now.tm_mon - 1], now.tm_year % 100)
    draw_text(buf, SPRITES['date'], datestr, LEFT, 110 + CLOCK_SZ + 36 + DATE_SZ + 36)

    # --- Top-right: temperature + condition ---
    if weather['temp'] is not None:
        temp = '%d°' % weather['temp']
        tw = text_width(SPRITES['big'], temp)
        draw_text(buf, SPRITES['big'], temp, W - tw - MARGIN, 110)
        dw = text_width(SPRITES['small'], weather['desc'])
        draw_text(buf, SPRITES['small'], weather['desc'], W - dw - MARGIN,
                  110 + BIG_SZ + 30)

    if test_mark:
        # Provenance test: solid 300x300 red square in the top-left corner
        for yy in range(300):
            row = buf[yy]
            for xx in range(300):
                o = xx * 3
                row[o] = 255
                row[o + 1] = 0
                row[o + 2] = 0
    return buf

def write_outputs(png):
    os.makedirs(OUT_DIR + '/4k', exist_ok=True)
    os.makedirs(OUT_DIR + '/2k', exist_ok=True)
    os.makedirs(OUT_DIR + '/hd', exist_ok=True)
    for sub in ('4k', '2k', 'hd'):
        with open('%s/%s/bg_banner_img.png' % (OUT_DIR, sub), 'wb') as f:
            f.write(png)

def main():
    log('bg-generator started pid=%d' % os.getpid())
    load_sprites()
    bg = make_background()
    log('background loaded %dx%d' % (W, H))
    weather = fetch_weather()
    if '--once' in sys.argv:
        png = png_encode(build(bg, weather, test_mark='--mark' in sys.argv))
        write_outputs(png)
        log('single render done (mark=%s)' % ('--mark' in sys.argv))
        return
    last_min = -1
    last_wx = 0
    last_rendered = None
    while True:
        now = time.time()
        tm = time.gmtime(now + TZ_OFFSET)
        cur_min = tm.tm_hour * 60 + tm.tm_min
        wx_due = (now - last_wx > 600
                  or (weather['temp'] is None and now - last_wx > 120))
        if wx_due:
            weather = fetch_weather()
            last_wx = now
            log('weather: %r' % (weather,))
        # Re-render when the minute or the weather changes
        sig = (cur_min, weather['temp'], weather['desc'])
        if sig != last_rendered:
            try:
                png = png_encode(build(bg, weather, now=tm))
                write_outputs(png)
                last_rendered = sig
                last_min = cur_min
                log('wallpaper updated: %r' % (sig,))
            except Exception as e:
                log('render error: %r' % e)
        time.sleep(15)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log('FATAL: %r' % e)
        raise
