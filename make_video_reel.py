"""Reels from stock video clips: a few shots in a row, one line of text on each,
crossfades between them and a music track underneath.

    from make_video_reel import build
    build([(clip, start_s, "LINE ONE"), (clip, start_s, "LINE TWO"), ...], music, out)

Style follows make_post.py: white bold caps, no full stop, no colours, no lines; the
video is softly darkened behind the text only, so it stays readable.
"""
import os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import make_post

W, H, SEG, FADE, FPS = 1080, 1920, 5.0, 0.5, 30
FONT = ImageFont.truetype(make_post.FONT, 92)
LH = 104


def overlay(text, out, y_center=0.66):
    """Transparent PNG: soft dark cloud behind the text + the text itself."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    words, lines, line = text.strip().rstrip(".").upper().split(), [], ""
    for w in words:
        t = (line + " " + w).strip()
        if probe.textlength(t, font=FONT) <= W - 160:
            line = t
        else:
            lines.append(line)
            line = w
    lines.append(line)
    y = int(H * y_center) - LH * len(lines) // 2
    bw = max(probe.textlength(l, font=FONT) for l in lines)
    shade = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shade).rectangle(((W - bw) / 2 - 60, y - 60, (W + bw) / 2 + 60, y + LH * len(lines) + 50), fill=150)
    shade = shade.filter(ImageFilter.GaussianBlur(70))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.putalpha(shade)
    d = ImageDraw.Draw(img)
    for l in lines:
        d.text((W / 2, y), l, font=FONT, fill=(240, 240, 240, 255), anchor="ma")
        y += LH
    img.save(out)


def shot(src, start, text, out):
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
        png = t.name
    overlay(text, png)
    subprocess.run([
        "ffmpeg", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(SEG), "-i", src, "-i", png,
        "-filter_complex",
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,"
        f"eq=contrast=1.05:saturation=0.85[v];[v][1:v]overlay=0:0,format=yuv420p",
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20", out], check=True)
    os.unlink(png)


def build(shots, music, out):
    tmp = tempfile.mkdtemp()
    parts = []
    for i, (src, start, text) in enumerate(shots):
        p = f"{tmp}/s{i}.mp4"
        shot(src, start, text, p)
        parts.append(p)
    chain, last, offset = "", "[0:v]", 0.0
    for i in range(1, len(parts)):
        offset += SEG - FADE
        chain += f"{last}[{i}:v]xfade=transition=fade:duration={FADE}:offset={offset:.2f}[x{i}];"
        last = f"[x{i}]"
    total = SEG * len(parts) - FADE * (len(parts) - 1)
    inputs = sum((["-i", p] for p in parts), [])
    if len(parts) == 1:
        chain, last = "[0:v]null[x0];", "[x0]"
    subprocess.run([
        "ffmpeg", "-loglevel", "error", "-y", *inputs, "-i", music, "-filter_complex",
        chain + f"[{len(parts)}:a]atrim=0:{total:.2f},afade=t=in:d=0.4,afade=t=out:st={total - 1.5:.2f}:d=1.5[a]",
        "-map", last, "-map", "[a]", "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        "-movflags", "+faststart", out], check=True)
    return total
