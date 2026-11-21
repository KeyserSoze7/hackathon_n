"""Vectorise assets/main logo.jpeg into clean SVGs.

Steps: upscale 4x (Lanczos, so edges get sub-pixel detail), snap every pixel to the logo's
measured palette (removes JPEG noise), then trace to SVG splines with vtracer.

Outputs (both one-to-one with the source geometry):
  assets/marg-logo.svg   full card, 430 x 512, same layout as the JPEG
  assets/marg-mark.svg   milestone emblem only, cropped tight, for headers and favicons
Usage: python frontend/scripts/vectorize_logo.py
"""
import pathlib
import re
import sys

import numpy as np
import vtracer
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / 'assets' / 'main logo.jpeg'
OUT = ROOT / 'assets'
SCALE = 4

# Measured from the JPEG (see the palette probe). Order does not matter.
PALETTE = {
    'outside': (255, 255, 255),
    'card': (243, 244, 246),
    'yellow': (248, 195, 1),
    'ink': (43, 49, 45),
    'track': (218, 223, 227),
}


def snap(img: Image.Image, track_rows: tuple[tuple[float, float], ...] = ()) -> Image.Image:
    """Snap pixels to the palette. Track grey only exists in the given row bands (fractions of height):
    elsewhere it would turn anti-aliased ink-on-white edges into false grey outlines."""
    a = np.asarray(img.convert('RGB')).astype(np.int32)
    names = list(PALETTE)
    pal = np.array(list(PALETTE.values()), dtype=np.int32)
    d = ((a[:, :, None, :] - pal[None, None, :, :]) ** 2).sum(-1)
    ti = names.index('track')
    allowed = np.zeros(a.shape[0], dtype=bool)
    for lo, hi in track_rows:
        allowed[int(lo * a.shape[0]):int(hi * a.shape[0])] = True
    d[~allowed, :, ti] = np.iinfo(np.int32).max
    return Image.fromarray(pal[d.argmin(-1)].astype(np.uint8), 'RGB')


def snap_fills(svg: str) -> str:
    """vtracer averages clustered colours; put every fill back on the exact palette."""
    pal = list(PALETTE.values())
    def fix(m: re.Match) -> str:
        h = m.group(1)
        c = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        best = min(pal, key=lambda p: sum((x - y) ** 2 for x, y in zip(c, p)))
        return 'fill="#%02X%02X%02X"' % best
    return re.sub(r'fill="#([0-9A-Fa-f]{6})"', fix, svg)


def border_light(a: np.ndarray) -> np.ndarray:
    """Mask of card-or-white pixels connected to the image border (the background)."""
    from PIL import ImageDraw
    light = np.all(a == PALETTE['card'], -1) | np.all(a == PALETTE['outside'], -1)
    m = Image.fromarray(np.where(light, 255, 0).astype(np.uint8), 'L').copy()  # copy: fromarray may share a read-only buffer
    W, H = m.size
    edge = [(x, y) for x in range(0, W, 8) for y in (0, H - 1)] + [(x, y) for y in range(0, H, 8) for x in (0, W - 1)]
    for p in edge:
        if m.getpixel(p) == 255:
            ImageDraw.floodfill(m, p, 128)
    return np.asarray(m) == 128


def trace(img: Image.Image, out: pathlib.Path, w: int, h: int, track_rows: tuple[tuple[float, float], ...] = (),
          transparent: tuple[int, int, int] | None = None) -> None:
    big = img.resize((w * SCALE, h * SCALE), Image.LANCZOS)
    q = snap(big, track_rows)
    a = np.asarray(q)
    # Background = every card-or-white pixel connected to the image border. Card grey never occurs
    # inside the emblem, so card pixels enclosed by it are edge noise next to white: make them white.
    bg = border_light(a)
    enclosed_card = np.all(a == PALETTE['card'], -1) & ~bg
    a = np.where(enclosed_card[..., None], np.array(PALETTE['outside'], dtype=np.uint8), a)
    if transparent is None:
        q = Image.fromarray(a, 'RGB')
    else:
        # Key out the background before tracing, so no backing shape is generated under it.
        a = np.where(bg[..., None], np.array(transparent, dtype=np.uint8), a)
        alpha = np.where(bg, 0, 255).astype(np.uint8)
        q = Image.fromarray(np.dstack([a, alpha]), 'RGBA')
    tmp = out.with_suffix('.tmp.png')
    q.save(tmp)
    vtracer.convert_image_to_svg_py(
        str(tmp), str(out), colormode='color', hierarchical='stacked', mode='spline',
        filter_speckle=8, color_precision=8, layer_difference=8, corner_threshold=60,
        length_threshold=4.0, max_iterations=10, splice_threshold=45, path_precision=1,
    )
    tmp.unlink()
    svg = out.read_text(encoding='utf-8')
    # Scale back to source units with a viewBox, so the file is resolution independent.
    svg = re.sub(r'<svg[^>]*>', f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w * SCALE} {h * SCALE}" width="{w}" height="{h}">', svg, count=1)
    svg = re.sub(r'<\?xml[^>]*>\s*', '', svg)
    svg = re.sub(r'<!--[^>]*-->\s*', '', svg)
    svg = svg.replace(' transform="translate(0,0)"', '')
    svg = snap_fills(svg)
    out.write_text(svg, encoding='utf-8')
    print(out.name, f'{out.stat().st_size / 1024:.1f} KB', svg.count('<path'), 'paths')


def main() -> None:
    src = Image.open(SRC).convert('RGB')
    w, h = src.size
    # Track grey appears only in the thin rule under the kerb (top ~3%) and the progress bar (bottom ~15%).
    trace(src, OUT / 'marg-logo.svg', w, h, track_rows=((0.0, 0.03), (0.85, 1.0)))

    # Emblem: bounding box of everything that is not card or outside, between the kerb and the progress bar.
    q = np.asarray(snap(src, ((0.0, 0.03), (0.85, 1.0))))
    body = ~(np.all(q == PALETTE['card'], -1) | np.all(q == PALETTE['outside'], -1))
    body[:30, :] = False   # kerb
    body[420:, :] = False  # progress bar
    ys, xs = np.where(body)
    pad = 2
    box = (max(xs.min() - pad, 0), max(ys.min() - pad, 0), min(xs.max() + pad + 1, w), min(ys.max() + pad + 1, h))
    print('emblem box', box)
    mark = src.crop(box)
    # Transparent background, so the emblem sits on any surface.
    trace(mark, OUT / 'marg-mark.svg', mark.width, mark.height, transparent=PALETTE['card'])


if __name__ == '__main__':
    sys.exit(main())
