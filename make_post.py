"""Put a quote on the hoodie background (1080x1350, Instagram 4:5).
Usage: python3 make_post.py "QUOTE TEXT" output.png [background.jpg]
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat

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


def best_spot(img, bw, bh):
    """Pick the darkest, calmest corner for the text so white text stays readable.
    Styling is unchanged; only the position adapts to the background."""
    gray = img.convert("L")
    spots = [(X0, H - BOTTOM - bh), (MARGIN, H - BOTTOM - bh),
             (X0, BOTTOM), (MARGIN, BOTTOM)]
    best = min(spots, key=lambda p: spot_score(gray, p[0], p[1], bw, bh))  # ties keep bottom-right
    return best, spot_score(gray, best[0], best[1], bw, bh)


def layout(img, text):
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
    (x, y), score = best_spot(img, block_w, lh * len(lines))
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
    score, bright = readability(text, bg)
    return score <= 55 and bright <= 0.005


def make(text, out, bg="background.jpg"):
    img = load_bg(bg)
    d = ImageDraw.Draw(img)
    font, lines, lh, x, y, _ = layout(img, text)
    for ln in lines:
        d.text((x, y), ln, font=font, fill=(240, 240, 240))
        y += lh
    img.save(out, quality=95)


if __name__ == "__main__":
    make(sys.argv[1], sys.argv[2], *(sys.argv[3:4]))
