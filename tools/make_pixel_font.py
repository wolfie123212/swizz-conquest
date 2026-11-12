#!/usr/bin/env python3
"""Builds the game's pixel font and embeds it in index.html.

Run from the game folder after adding or changing a character below:
    python3 tools/make_pixel_font.py

Each character is listed as rows of pixels, top to bottom, as hex numbers
(5 pixels wide for letters, 7 for icons). The font is 8 pixels to the em, so
it's crisp at any size that's a multiple of 8 pixels on screen.
"""
import base64
import re
import struct
import time

UNIT = 128   # font units per pixel
EM = UNIT * 8

LETTERS = {
    "A": "0E 11 11 1F 11 11 11", "B": "1E 11 11 1E 11 11 1E", "C": "0E 11 10 10 10 11 0E",
    "D": "1E 11 11 11 11 11 1E", "E": "1F 10 10 1E 10 10 1F", "F": "1F 10 10 1E 10 10 10",
    "G": "0E 11 10 17 11 11 0F", "H": "11 11 11 1F 11 11 11", "I": "0E 04 04 04 04 04 0E",
    "J": "07 02 02 02 02 12 0C", "K": "11 12 14 18 14 12 11", "L": "10 10 10 10 10 10 1F",
    "M": "11 1B 15 15 11 11 11", "N": "11 19 15 13 11 11 11", "O": "0E 11 11 11 11 11 0E",
    "P": "1E 11 11 1E 10 10 10", "Q": "0E 11 11 11 15 12 0D", "R": "1E 11 11 1E 14 12 11",
    "S": "0F 10 10 0E 01 01 1E", "T": "1F 04 04 04 04 04 04", "U": "11 11 11 11 11 11 0E",
    "V": "11 11 11 11 11 0A 04", "W": "11 11 11 15 15 1B 11", "X": "11 11 0A 04 0A 11 11",
    "Y": "11 11 0A 04 04 04 04", "Z": "1F 01 02 04 08 10 1F",
}
DIGITS = {
    "0": "0E 11 13 15 19 11 0E", "1": "04 0C 04 04 04 04 0E", "2": "0E 11 01 06 08 10 1F",
    "3": "1F 02 04 02 01 11 0E", "4": "02 06 0A 12 1F 02 02", "5": "1F 10 1E 01 01 11 0E",
    "6": "06 08 10 1E 11 11 0E", "7": "1F 01 02 04 08 08 08", "8": "0E 11 11 0E 11 11 0E",
    "9": "0E 11 11 0F 01 02 0C",
}
PUNCTUATION = {
    ".": "00 00 00 00 00 0C 0C", ",": "00 00 00 00 00 04 04 08", ":": "00 0C 0C 00 0C 0C 00",
    ";": "00 0C 0C 00 0C 04 08", "!": "04 04 04 04 04 00 04", "?": "0E 11 01 02 04 00 04",
    "'": "04 04 08 00 00 00 00", '"': "0A 0A 00 00 00 00 00", "-": "00 00 00 1F 00 00 00",
    "−": "00 00 00 1F 00 00 00", "+": "00 04 04 1F 04 04 00", "/": "01 02 02 04 08 08 10",
    "%": "18 19 02 04 08 13 03", "(": "02 04 08 08 08 04 02", ")": "08 04 02 02 02 04 08",
    "=": "00 00 1F 00 1F 00 00", "_": "00 00 00 00 00 00 1F", "&": "0C 12 14 08 15 12 0D",
    "*": "00 04 15 0E 15 04 00", "#": "0A 0A 1F 0A 1F 0A 0A", "<": "02 04 08 10 08 04 02",
    ">": "08 04 02 01 02 04 08",
}
ICONS = {
    # Nation emblems
    "★": "08 08 7F 3E 1C 36 63", "◆": "08 1C 3E 7F 3E 1C 08", "⬢": "1C 3E 63 63 63 3E 1C",
    "✦": "08 08 1C 7F 1C 08 08", "▲": "08 08 1C 1C 3E 3E 7F", "●": "1C 3E 7F 7F 7F 3E 1C",
    "■": "7F 7F 7F 7F 7F 7F 7F", "✚": "1C 1C 7F 7F 7F 1C 1C", "▼": "7F 3E 3E 1C 1C 08 08",
    # Buildings, in the private-use area: city, mine, lab, trader, station
    "": "0C 0C 6C 6F 6F 7F 7F", "": "1C 02 05 09 10 20 40", "": "1C 08 08 14 22 5D 7F",
    "": "01 02 24 58 40 00 7F", "": "08 3E 7F 41 5D 5D 55",
    # Extra building icons: port, SAM, fort, silo, submarine
    "\uE005": "08 1C 08 08 49 49 3E", "\uE006": "41 22 1C 08 08 1C 3E", "\uE007": "55 7F 7F 63 63 7F 7F",
    "\uE008": "08 1C 1C 1C 1C 3E 6B", "\uE009": "00 08 1C 7F 7F 3E 00",
    # Radiation, crossed swords (troops), radio tower (alliances)
    "\uE00A": "36 77 63 08 00 1C 3E", "\uE00B": "41 22 14 08 14 36 63", "\uE00C": "49 2A 08 1C 14 36 22",
}


def glyph_from(rows_hex, width, keep_side_gaps=False):
    """Returns (list of (x, y, w, h) pixel runs, advance in pixels)."""
    rows = [int(r, 16) for r in rows_hex.split()]
    cells = [[bool(row >> (width - 1 - x) & 1) for x in range(width)] for row in rows]
    columns = [x for x in range(width) if any(row[x] for row in cells)]
    first = 0 if keep_side_gaps else (columns[0] if columns else 0)
    last = width - 1 if keep_side_gaps else (columns[-1] if columns else 0)
    runs = []
    for r, row in enumerate(cells):
        y = 6 - r                 # the seventh row sits on the baseline
        x = 0
        while x < width:
            if row[x]:
                start = x
                while x < width and row[x]:
                    x += 1
                runs.append((start - first, y, x - start, 1))
            else:
                x += 1
    return runs, last - first + 2


glyphs = [([], 6)]                # glyph 0 is the blank fallback
cmap = {}


def add(char, rows, width, keep_side_gaps=False):
    glyphs.append(glyph_from(rows, width, keep_side_gaps))
    cmap[ord(char)] = len(glyphs) - 1


glyphs.append(([], 4))
cmap[ord(" ")] = 1
for char, rows in LETTERS.items():
    add(char, rows, 5)
    cmap[ord(char.lower())] = len(glyphs) - 1   # lower case uses the same shapes
for char, rows in DIGITS.items():
    add(char, rows, 5, keep_side_gaps=True)     # equal widths keep numbers from jiggling
for char, rows in PUNCTUATION.items():
    add(char, rows, 5)
for char, rows in ICONS.items():
    add(char, rows, 7)


def encode_glyph(runs):
    if not runs:
        return b""
    xs = [x for x, _, w, _ in runs] + [x + w for x, _, w, _ in runs]
    ys = [y for _, y, _, h in runs] + [y + h for _, y, _, h in runs]
    box = [min(xs) * UNIT, min(ys) * UNIT, max(xs) * UNIT, max(ys) * UNIT]
    points = []
    for x, y, w, h in runs:    # clockwise, as TrueType expects
        points += [(x, y), (x, y + h), (x + w, y + h), (x + w, y)]
    data = struct.pack(">hhhhh", len(runs), *box)
    for i in range(len(runs)):
        data += struct.pack(">H", i * 4 + 3)
    data += struct.pack(">H", 0)
    data += bytes([0x01]) * len(points)
    px, deltas_x, deltas_y = 0, b"", b""
    py = 0
    for x, y in points:
        deltas_x += struct.pack(">h", (x - px) * UNIT)
        deltas_y += struct.pack(">h", (y - py) * UNIT)
        px, py = x, y
    data += deltas_x + deltas_y
    return data + b"\0" * (-len(data) % 4)


glyf, loca = b"", [0]
for runs, _ in glyphs:
    glyf += encode_glyph(runs)
    loca.append(len(glyf))

ascent, descent = UNIT * 8, -UNIT * 2
now = int(time.time()) + 2082844800      # font dates count from 1904

codes = sorted(cmap)
seg_count = len(codes) + 1
search = 2 ** (seg_count.bit_length() - 1) * 2
cmap_sub = struct.pack(">HHHHHHH", 4, 16 + seg_count * 8, 0, seg_count * 2, search,
                       seg_count.bit_length() - 1, seg_count * 2 - search)
cmap_sub += b"".join(struct.pack(">H", c) for c in codes) + struct.pack(">HH", 0xFFFF, 0)
cmap_sub += b"".join(struct.pack(">H", c) for c in codes) + struct.pack(">H", 0xFFFF)
cmap_sub += b"".join(struct.pack(">H", (cmap[c] - c) & 0xFFFF) for c in codes) + struct.pack(">H", 1)
cmap_sub += b"\0\0" * seg_count


def name_table():
    names = {1: "SwizzPixel", 2: "Regular", 3: "SwizzPixel Regular", 4: "SwizzPixel", 6: "SwizzPixel-Regular"}
    records, strings = b"", b""
    for name_id, text in names.items():
        encoded = text.encode("utf-16-be")
        records += struct.pack(">HHHHHH", 3, 1, 0x409, name_id, len(encoded), len(strings))
        strings += encoded
    return struct.pack(">HHH", 0, len(names), 6 + len(records)) + records + strings


tables = {
    b"OS/2": struct.pack(">HhHHH10hh10s4I4sHHHhhhHH2I", 1, 6 * UNIT, 400, 5, 0,
                         0, 0, 0, 0, 0, 0, 0, 0, UNIT, 3 * UNIT, 0, b"\0" * 10, 0, 0, 0, 0, b"SWZP", 0x40,
                         min(codes), min(max(codes), 0xFFFF), ascent, descent, 0, ascent, -descent, 1, 0),
    b"cmap": struct.pack(">HHHHI", 0, 1, 3, 1, 12) + cmap_sub,
    b"glyf": glyf,
    b"head": struct.pack(">IIIIHHQQhhhhHHhhh", 0x00010000, 0x00010000, 0, 0x5F0F3CF5, 0x000B, EM, now, now,
                         0, descent, 8 * UNIT, ascent, 0, 8, 2, 1, 0),
    b"hhea": struct.pack(">IhhhHhhhhhhhhhhhH", 0x00010000, ascent, descent, 0, 8 * UNIT, 0, 0, 8 * UNIT,
                         1, 0, 0, 0, 0, 0, 0, 0, len(glyphs)),
    b"hmtx": b"".join(struct.pack(">Hh", adv * UNIT, 0) for _, adv in glyphs),
    b"loca": b"".join(struct.pack(">I", o) for o in loca),
    b"maxp": struct.pack(">IHHHHHHHHHHHHHH", 0x00010000, len(glyphs),
                         max(len(r) * 4 for r, _ in glyphs), max(len(r) for r, _ in glyphs),
                         0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0),
    b"name": name_table(),
    b"post": struct.pack(">IIhhIIIII", 0x00030000, 0, -UNIT, UNIT, 0, 0, 0, 0, 0),
}


def checksum(data):
    data += b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(data) // 4}I", data)) & 0xFFFFFFFF


def build(head_adjust=0):
    entry = 2 ** (len(tables).bit_length() - 1)
    header = struct.pack(">IHHHH", 0x00010000, len(tables), entry * 16,
                         len(tables).bit_length() - 1, len(tables) * 16 - entry * 16)
    directory, body = b"", b""
    offset = 12 + 16 * len(tables)
    for tag in sorted(tables):
        data = tables[tag]
        if tag == b"head":
            data = data[:8] + struct.pack(">I", head_adjust) + data[12:]
        directory += tag + struct.pack(">III", checksum(tables[tag]), offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    return header + directory + body


font = build()
font = build((0xB1B0AFBA - checksum(font)) & 0xFFFFFFFF)

encoded = base64.b64encode(font).decode()
page = open("index.html", encoding="utf-8").read()
page, count = re.subn(r"url\(data:font/ttf;base64,[^)]*\)", f"url(data:font/ttf;base64,{encoded})", page)
if count != 1:
    raise SystemExit("Couldn't find the @font-face line in index.html")
open("index.html", "w", encoding="utf-8").write(page)
print(f"Font built: {len(glyphs)} shapes, {len(font)} bytes")
