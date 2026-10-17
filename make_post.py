"""Put a quote on the hoodie background (1080x1350, Instagram 4:5).
Usage: python3 make_post.py "QUOTE TEXT" output.png [background.jpg]
"""
import sys
from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 1080, 1350
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"
X0, MAX_W, BOTTOM = 500, 540, 120  # text block sits in the dark area, bottom right


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


def make(text, out, bg="background.jpg"):
    img = ImageOps.fit(Image.open(bg).convert("RGB"), (W, H), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    text = text.upper()
    for size in range(78, 40, -2):
        font = ImageFont.truetype(FONT, size)
        lines = wrap(text, font, d)
        lh = int(size * 1.13)
        if lh * len(lines) <= H * 0.5:
            break
    y = H - BOTTOM - lh * len(lines)
    for ln in lines:
        d.text((X0, y), ln, font=font, fill=(240, 240, 240))
        y += lh
    img.save(out, quality=95)


if __name__ == "__main__":
    make(sys.argv[1], sys.argv[2], *(sys.argv[3:4]))
