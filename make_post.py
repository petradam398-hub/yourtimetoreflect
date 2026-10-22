"""Put a quote on the hoodie background (1080x1350, Instagram 4:5).
Usage: python3 make_post.py "QUOTE TEXT" output.png [background.jpg]
"""
import os, sys
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

W, H = 1080, 1350
FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "DejaVuSansCondensed-Bold.ttf")
X0, MAX_W, BOTTOM = 500, 540, 120  # default: text block bottom right
MARGIN = 60  # for the other candidate corners


def wrap(text, font, d):
    """Balanced wrap: minimise uneven line lengths instead of filling greedily."""
    words = text.split()
    n = len(words)
    best = [0.0] + [float("inf")] * n
    prev = [0] * (n + 1)
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            w = d.textlength(" ".join(words[i:j]), font=font)
            if w > MAX_W:
                break
            cost = best[i] + (MAX_W - w) ** 2
            if cost < best[j]:
                best[j], prev[j] = cost, i
    lines, j = [], n
    while j > 0:
        lines.insert(0, " ".join(words[prev[j]:j]))
        j = prev[j]
    return lines


def spot_score(gray, x, y, bw, bh):
    """Lower is better: dark and calm behind the text block."""
    st = ImageStat.Stat(gray.crop((int(x) - 20, int(y) - 20, int(x + bw) + 20, int(y + bh) + 20)))
    return st.mean[0] + 0.5 * st.stddev[0]


SPOTS = ("bottom-right", "bottom-left", "top-right", "top-left")


def best_spot(img, bw, bh, spot=None):
    """Pick the darkest, calmest corner for the text so white text stays readable.
    Styling is unchanged; only the position adapts to the background."""
    gray = img.convert("L")
    spots = [(X0, H - BOTTOM - bh), (MARGIN, H - BOTTOM - bh),
             (X0, BOTTOM), (MARGIN, BOTTOM)]
    if spot in SPOTS:  # fixed position, e.g. to keep the text off a face
        spots = [spots[SPOTS.index(spot)]]
    best = min(spots, key=lambda p: spot_score(gray, p[0], p[1], bw, bh))  # ties keep bottom-right
    return best, spot_score(gray, best[0], best[1], bw, bh)


def layout(img, text, spot=None):
    d = ImageDraw.Draw(img)
    text = text.strip().rstrip(".").upper()  # no full stop at the end, ever
    for size in range(78, 40, -2):
        font = ImageFont.truetype(FONT, size)
        lines = wrap(text, font, d)
        lh = int(size * 1.13)
        fits_width = all(d.textlength(ln, font=font) <= MAX_W for ln in lines)
        if fits_width and lh * len(lines) <= H * 0.5:
            break
    block_w = max(d.textlength(ln, font=font) for ln in lines)
    (x, y), score = best_spot(img, block_w, lh * len(lines), spot)
    return font, lines, lh, x, y, score


def load_bg(bg):
    return ImageOps.fit(Image.open(bg).convert("RGB"), (W, H), Image.LANCZOS)


def readability(text, bg):
    """(score, bright share) behind the text at its best spot. Lower is easier to read.
    bright share = part of the area under the text lighter than mid-grey, which catches
    text sitting over a face, a hood or a lamp even when the average looks dark."""
    img = load_bg(bg)
    font, lines, lh, x, y, score = layout(img, text)
    bw = max(ImageDraw.Draw(img).textlength(ln, font=font) for ln in lines)
    hist = img.convert("L").crop((int(x) - 20, int(y) - 20, int(x + bw) + 20, int(y + lh * len(lines)) + 20)).histogram()
    return score, sum(hist[110:]) / sum(hist)


def is_readable(text, bg):
    """True if the text reads well on the photo as it is (no darkening needed)."""
    score, bright = readability(text, bg)
    return score <= 55 and bright <= 0.005


def block_box(img, font, lines, lh, x, y):
    bw = max(ImageDraw.Draw(img).textlength(ln, font=font) for ln in lines)
    return int(x) - 20, int(y) - 20, int(x + bw) + 20, int(y + lh * len(lines)) + 20


def area_ok(img, box):
    g = img.convert("L").crop(box)
    st, hist = ImageStat.Stat(g), g.histogram()
    return st.mean[0] + 0.5 * st.stddev[0] <= 55 and sum(hist[110:]) / sum(hist) <= 0.005


def darken_behind(img, box):
    """Softly darken the photo behind the text (no box, no colour, no hard edge),
    just enough for white text to read. Photos that are already dark stay untouched."""
    if area_ok(img, box):
        return img
    mask = Image.new("L", img.size, 0)
    x0, y0, x1, y1 = box
    ImageDraw.Draw(mask).rectangle((x0 - 60, y0 - 60, x1 + 60, y1 + 60), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(90))
    black = Image.new("RGB", img.size, (0, 0, 0))
    out = img
    for strength in (0.35, 0.5, 0.6, 0.7, 0.78, 0.85):
        m = mask.point(lambda v: int(v * strength))
        out = Image.composite(black, img, m)
        if area_ok(out, box):
            break
    return out


def make(text, out, bg="background.jpg", spot=None):
    img = load_bg(bg)
    font, lines, lh, x, y, _ = layout(img, text, spot)
    img = darken_behind(img, block_box(img, font, lines, lh, x, y))
    d = ImageDraw.Draw(img)
    for ln in lines:
        d.text((x, y), ln, font=font, fill=(240, 240, 240))
        y += lh
    img.save(out, quality=95)


if __name__ == "__main__":
    make(sys.argv[1], sys.argv[2], *(sys.argv[3:4]))
