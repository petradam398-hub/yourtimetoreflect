"""Carousel posts ("5 rules every man should know"): a cover slide, one slide per point
and a closing slide, each on one of our photos. 1080x1350 JPEGs, same style as the
posts: white bold caps, no colours, no full stop at the end of headlines.

    build("carousels/c01", "5 rules every man should know",
          [("Keep your word", "If you say it, do it. ..."), ...],
          ["backgrounds/a.jpg", ...])   # one photo per slide: cover + points + end
"""
import os
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

import make_post

W, H = 1080, 1350
BOLD = make_post.FONT
WHITE, GREY = (240, 240, 240), (190, 190, 190)


def f(size):
    return ImageFont.truetype(BOLD, size)


def wrap(d, text, font, max_w):
    lines, line = [], ""
    for w in text.split():
        t = (line + " " + w).strip()
        if d.textlength(t, font=font) <= max_w:
            line = t
        else:
            lines.append(line)
            line = w
    lines.append(line)
    return lines


def fit(d, text, size, max_w, max_lines):
    while True:
        lines = wrap(d, text, f(size), max_w)
        if len(lines) <= max_lines and all(d.textlength(l, font=f(size)) <= max_w for l in lines):
            return f(size), lines
        size -= 4


def base(photo, dim=0.5):
    img = ImageOps.fit(Image.open(photo).convert("RGB"), (W, H), Image.LANCZOS)
    return ImageEnhance.Brightness(img).enhance(dim)  # text-heavy slides: darken the whole photo


def block(img, lines, font, y, lh, fill=WHITE, align="center", x=None):
    d = ImageDraw.Draw(img)
    for l in lines:
        if align == "center":
            d.text((W / 2, y), l, font=font, fill=fill, anchor="ma")
        else:
            d.text((x, y), l, font=font, fill=fill)
        y += lh
    return y


def cover(photo, title, out):
    img = base(photo, 0.55)
    d = ImageDraw.Draw(img)
    font, lines = fit(d, title.upper(), 120, W - 160, 5)
    lh = int(font.size * 1.12)
    y = H * 0.46 - lh * len(lines) / 2
    img = make_post.darken_behind(img, (60, int(y) - 30, W - 60, int(y + lh * len(lines)) + 30))
    block(img, lines, font, y, lh)
    block(img, ["SWIPE  >>"], f(44), H - 150, 50, fill=GREY)
    img.save(out, quality=92)


def point(photo, n, total, head, body, out):
    img = base(photo, 0.42)
    d = ImageDraw.Draw(img)
    x = 90
    hf, hl = fit(d, head.strip().rstrip(".").upper(), 92, W - 2 * x, 3)
    bl_ = wrap(d, body, f(52), W - 2 * x)
    bottom = 500 + int(hf.size * 1.12) * len(hl) + 50 + 66 * len(bl_)
    img = make_post.darken_behind(img, (x - 30, 180, W - x + 30, bottom + 20))
    d = ImageDraw.Draw(img)
    d.text((x, 200), f"{n}", font=f(220), fill=WHITE)
    y = block(img, hl, hf, 500, int(hf.size * 1.12), align="left", x=x)
    bf = f(52)
    bl = wrap(d, body, bf, W - 2 * x)
    block(img, bl, bf, y + 50, 66, fill=GREY, align="left", x=x)
    d.text((W - 90, H - 110), f"{n}/{total}", font=f(40), fill=GREY, anchor="ra")
    img.save(out, quality=92)


def ending(photo, out):
    img = base(photo, 0.5)
    img = make_post.darken_behind(img, (80, int(H * 0.36) - 30, W - 80, int(H * 0.36) + 430))
    y = block(img, ["SAVE THIS", "FOR LATER"], f(110), H * 0.36, 124)
    block(img, ["SEND IT TO A FRIEND", "WHO NEEDS IT"], f(60), y + 70, 74, fill=GREY)
    block(img, ["@YOURTIMETOREFLECT"], f(46), H - 170, 52, fill=GREY)
    img.save(out, quality=92)


def build(folder, title, points, photos):
    os.makedirs(folder, exist_ok=True)
    slides = [f"{folder}/{i + 1:02d}.jpg" for i in range(len(points) + 2)]
    cover(photos[0], title, slides[0])
    for i, (head, body) in enumerate(points, 1):
        point(photos[i], i, len(points), head, body, slides[i])
    ending(photos[len(points) + 1], slides[-1])
    return slides
