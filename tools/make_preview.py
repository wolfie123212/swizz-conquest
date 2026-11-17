#!/usr/bin/env python3
"""Draws preview.png, the picture shown when the game's link is shared
(in iMessage, Discord and so on).

Run from the game folder:
    python3 tools/make_preview.py

It uses the same 5x7 letters as the game's pixel font, so no image library is needed.
"""
import math
import random
import re
import struct
import zlib

W, H = 1200, 630
CELL = 10                      # map pixels are drawn as 10x10 blocks
OCEAN = (22, 14, 38)
OCEAN_DEEP = (16, 10, 30)
NATIONS = [(255, 107, 107), (62, 230, 193), (255, 209, 102), (124, 140, 255), (198, 107, 255), (126, 220, 90)]
FREE_LAND = (74, 60, 104)
GOLD = (255, 209, 102)
WHITE = (241, 236, 255)
SOFT = (179, 164, 214)


def read_letters():
    """The letter shapes from the font tool: each is 7 rows of 5 pixels, as hex."""
    text = open("tools/make_pixel_font.py").read()
    shapes = {}
    for block in ("LETTERS", "DIGITS"):
        body = re.search(block + r" = \{(.*?)\n\}", text, re.S)
        if body:
            for char, rows in re.findall(r'"(.)": "([0-9A-F ]+)"', body.group(1)):
                shapes[char] = [int(r, 16) for r in rows.split()]
    return shapes


def main():
    random.seed(7)
    pixels = [[OCEAN] * W for _ in range(H)]

    def block(x, y, w, h, color):
        for yy in range(max(0, y), min(H, y + h)):
            row = pixels[yy]
            for xx in range(max(0, x), min(W, x + w)):
                row[xx] = color

    # A blobby continent made of a few overlapping circles, split between nations.
    cols, rows = W // CELL, H // CELL
    blobs = [(random.uniform(10, cols - 10), random.uniform(8, rows - 8), random.uniform(9, 17)) for _ in range(9)]
    capitals = [(random.uniform(8, cols - 8), random.uniform(6, rows - 6)) for _ in NATIONS]
    for cy in range(rows):
        for cx in range(cols):
            wobble = math.sin(cx * .7) * 1.2 + math.cos(cy * .9) * 1.2
            if not any(math.hypot(cx - bx, cy - by) < r + wobble for bx, by, r in blobs):
                if (cx * 7 + cy * 13) % 17 == 0:
                    block(cx * CELL, cy * CELL, CELL, CELL, OCEAN_DEEP)
                continue
            dists = sorted((math.hypot(cx - px, cy - py), i) for i, (px, py) in enumerate(capitals))
            color = NATIONS[dists[0][1]] if dists[0][0] < 14 else FREE_LAND
            if color != FREE_LAND:
                color = tuple(int(c * .55) for c in color)       # land is a darker shade of the nation's colour
            block(cx * CELL, cy * CELL, CELL, CELL, color)
            if dists[0][0] < 14 and dists[1][0] - dists[0][0] < 1.2:   # bright border between nations
                block(cx * CELL, cy * CELL, CELL, CELL, NATIONS[dists[0][1]])

    # A dark band behind the words so they read clearly.
    band_y, band_h = 190, 250
    for yy in range(band_y, band_y + band_h):
        for xx in range(W):
            r, g, b = pixels[yy][xx]
            pixels[yy][xx] = (r // 4 + 8, g // 4 + 5, b // 4 + 14)

    shapes = read_letters()

    def write(text, scale, y, color):
        width = len(text) * 6 * scale - scale
        x = (W - width) // 2
        for char in text:
            shape = shapes.get(char)
            if shape:
                for row, bits in enumerate(shape):
                    for col in range(5):
                        if bits & (1 << (4 - col)):
                            block(x + col * scale + scale // 3, y + row * scale + scale // 3, scale, scale, (40, 24, 60))   # shadow
                            block(x + col * scale, y + row * scale, scale, scale, color)
            x += 6 * scale

    write("SWIZZ CONQUEST", 12, 225, GOLD)
    write("CONQUER THE PLANET", 5, 345, WHITE)
    write("DIG TO THE CORE OR LAUNCH A ROCKET", 3, 395, SOFT)

    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in pixels)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    open("preview.png", "wb").write(png)
    print(f"Wrote preview.png ({len(png) // 1024} KB)")


if __name__ == "__main__":
    main()
