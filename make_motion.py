"""Motion-graphics reels generated entirely in code (no footage).

  kinetic(words_per_step, music, out)  - words pop in on the music's beats over drifting fog
  year_progress(date, music, out)      - "2026 IS 83% OVER" bar that fills up, then a question

Same style rules as the photo posts: white bold caps, no colours, no full stop at the end.
"""
import datetime, os, subprocess, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import make_post

W, H, FPS = 1080, 1920, 30
WHITE = (240, 240, 240)
FONT_PATH = make_post.FONT


def font(size):
    return ImageFont.truetype(FONT_PATH, size)


# ---------- shared background: slow fog, vignette, film grain ----------

def fog_layers(seed=3):
    rng = np.random.default_rng(seed)
    layers = []
    for scale in (6, 14):
        small = rng.random((H // 60 * scale // 6 + 2, W // 60 * scale // 6 + 2))
        img = Image.fromarray((small * 255).astype(np.uint8)).resize((W * 2, H), Image.BICUBIC)
        layers.append(np.asarray(img.filter(ImageFilter.GaussianBlur(60)), dtype=np.float32) / 255)
    yy, xx = np.mgrid[0:H, 0:W]
    vignette = 1 - 0.75 * np.clip(np.hypot((xx - W / 2) / (W * 0.75), (yy - H * 0.52) / (H * 0.62)), 0, 1) ** 2
    return layers, vignette.astype(np.float32)


def background(t, layers, vignette, rng, glow=0.0):
    a, b = layers
    sx1 = int((t * 18) % W)
    sx2 = int((W - t * 30) % W)
    fog = 0.6 * a[:, sx1:sx1 + W] + 0.4 * b[:, sx2:sx2 + W]
    base = 8 + 62 * fog ** 2 * (1 + glow)
    base = base * vignette + rng.normal(0, 4, (H, W)).astype(np.float32)
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "L").convert("RGB")


# ---------- beat detection (for the kinetic text) ----------

def onsets(music, seconds):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", music, "-t", str(seconds), "-ac", "1",
                          "-ar", "22050", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    hop = 512
    env = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x) - hop, hop)])
    flux = np.maximum(0, np.diff(env, prepend=env[0]))
    thr = np.convolve(flux, np.ones(20) / 20, mode="same") * 1.6 + flux.mean() * 0.5
    peaks = [i for i in range(1, len(flux) - 1) if flux[i] > thr[i] and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]]
    times, last = [], -1
    for p in peaks:
        t = p * hop / 22050
        if t - last >= 0.32:
            times.append(t)
            last = t
    return times


def encode(frames_dir, music, seconds, out):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", f"{frames_dir}/%04d.jpg",
                    "-i", music, "-filter_complex",
                    f"[1:a]atrim=0:{seconds},afade=t=in:d=0.3,afade=t=out:st={seconds - 1.5}:d=1.5[a]",
                    "-map", "0:v", "-map", "[a]", "-t", str(seconds), "-c:v", "libx264", "-preset", "medium",
                    "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
                    "-movflags", "+faststart", out], check=True)


def centered(d, lines, f, y_mid, lh, fill=WHITE):
    while max(d.textlength(l, font=f) for l in lines) > W - 160:  # keep a margin on both sides
        lh = lh * (f.size - 4) / f.size
        f = font(f.size - 4)
    y = y_mid - lh * len(lines) / 2
    for l in lines:
        d.text((W / 2, y), l, font=f, fill=fill, anchor="ma")
        y += lh


# ---------- 1) kinetic typography ----------

def kinetic(steps, music, out, seconds=13.0, seed=3, final=None):
    """steps: short phrases, each appears on a beat. final=(small line, big line) is the
    closing card shown after the last phrase, so the whole message reads at the end."""
    beats = [t for t in onsets(music, seconds) if t > 0.6]
    # spread the phrases over the beats so the last one lands around 70 % of the video
    end = seconds * 0.7
    usable = [t for t in beats if t <= end] or [i * end / len(steps) for i in range(len(steps))]
    pick = [usable[round(i * (len(usable) - 1) / max(1, len(steps) - 1))] for i in range(len(steps))]
    layers, vig = fog_layers(seed)
    rng = np.random.default_rng(seed)
    tmp = tempfile.mkdtemp()
    big = font(150)
    for n in range(int(seconds * FPS)):
        t = n / FPS
        shown = [i for i, s in enumerate(pick) if s <= t]
        glow = 0.0
        if shown:
            dt = t - pick[shown[-1]]
            glow = max(0.0, 0.5 - dt) * 0.9  # flash of light on every new word
        img = background(t, layers, vig, rng, glow)
        if final and shown and len(shown) == len(steps) and t - pick[-1] > 0.9:
            d = ImageDraw.Draw(img)
            b = min(1, (t - pick[-1] - 0.9) / 0.4)
            fb = big
            while d.textlength(final[1].upper(), font=fb) > W - 160:  # keep a margin on both sides
                fb = font(fb.size - 6)
            fs = font(70)
            while d.textlength(final[0].upper(), font=fs) > W - 160:
                fs = font(fs.size - 4)
            d.text((W / 2, H * 0.44), final[0].upper(), font=fs, fill=(int(170 * b),) * 3, anchor="mm")
            d.text((W / 2, H * 0.51), final[1].upper(), font=fb, fill=(int(240 * b),) * 3, anchor="mm")
        elif shown:
            i = shown[-1]
            dt = t - pick[i]
            phrase = steps[i].upper()
            scale = 1.0 + 0.12 * max(0.0, 1 - dt / 0.18)  # quick pop, then settle
            f = font(int(150 * scale)) if scale > 1.001 else big
            d = ImageDraw.Draw(img)
            # earlier phrases stay as a faint stack above the current one
            for j, prev in enumerate(steps[:i][-3:]):
                k = len(steps[:i][-3:]) - j
                d.text((W / 2, H * 0.47 - k * 120), prev.upper(), font=font(70), fill=(110, 110, 110), anchor="mm")
            d.text((W / 2, H * 0.5), phrase, font=f, fill=WHITE, anchor="mm")
        img.save(f"{tmp}/{n + 1:04d}.jpg", quality=90)
    encode(tmp, music, seconds, out)


# ---------- 2) year progress ----------

def year_progress(day, music, out, seconds=12.0, seed=5):
    start = datetime.date(day.year, 1, 1)
    total = (datetime.date(day.year + 1, 1, 1) - start).days
    pct = int((day - start).days / total * 100)
    left = total - (day - start).days
    layers, vig = fog_layers(seed)
    rng = np.random.default_rng(seed)
    tmp = tempfile.mkdtemp()
    f_title, f_pct, f_small, f_q = font(96), font(230), font(56), font(84)
    bar_w, bar_h, bar_y = 820, 46, int(H * 0.53)
    for n in range(int(seconds * FPS)):
        t = n / FPS
        img = background(t, layers, vig, rng)
        d = ImageDraw.Draw(img)
        fill = min(1.0, max(0.0, (t - 0.8) / 4.5))
        fill = 1 - (1 - fill) ** 3  # ease out
        cur = pct * fill
        a = int(255 * min(1, t / 0.6))
        d.text((W / 2, H * 0.30), f"{day.year} IS", font=f_title, fill=(a * 240 // 255,) * 3, anchor="mm")
        d.text((W / 2, H * 0.42), f"{cur:.0f}%", font=f_pct, fill=WHITE, anchor="mm")
        x0 = (W - bar_w) // 2
        d.rounded_rectangle((x0, bar_y, x0 + bar_w, bar_y + bar_h), radius=bar_h // 2, outline=(200, 200, 200), width=4)
        if cur > 0.5:
            d.rounded_rectangle((x0 + 8, bar_y + 8, x0 + 8 + int((bar_w - 16) * cur / 100), bar_y + bar_h - 8),
                                radius=(bar_h - 16) // 2, fill=WHITE)
        d.text((W / 2, bar_y + 120), "OVER", font=f_title, fill=WHITE, anchor="mm")
        if t > 6.2:
            b = min(1, (t - 6.2) / 0.6)
            g = int(240 * b)
            d.text((W / 2, H * 0.74), f"{left} DAYS LEFT", font=f_small, fill=(int(160 * b),) * 3, anchor="mm")
            centered(d, ["WHAT WILL YOU", "DO WITH THEM"], f_q, H * 0.83, 98, fill=(g, g, g))
        img.save(f"{tmp}/{n + 1:04d}.jpg", quality=90)
    encode(tmp, music, seconds, out)
    return pct, left


# ---------- 3) counter ----------

def counter(top, value, below, final, music, out, suffix="", seconds=12.0, seed=11):
    """top lines, then a number counting up from 0 to value (with suffix), lines below,
    and a closing line that fades in at the end."""
    layers, vig = fog_layers(seed)
    rng = np.random.default_rng(seed)
    tmp = tempfile.mkdtemp()
    f_top, f_num, f_below, f_final = font(80), font(210), font(80), font(92)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    suffix = suffix.upper()
    end_txt = f"{value:,}{suffix}".replace(",", " ")
    while probe.textlength(end_txt, font=f_num) > W - 140:
        f_num = font(f_num.size - 8)
    for n in range(int(seconds * FPS)):
        t = n / FPS
        img = background(t, layers, vig, rng)
        d = ImageDraw.Draw(img)
        a = min(1, t / 0.6)
        centered(d, [l.upper() for l in top], f_top, H * 0.27, 92, fill=(int(220 * a),) * 3)
        p = min(1.0, max(0.0, (t - 1.0) / 4.0))
        p = 1 - (1 - p) ** 3
        cur = int(round(value * p))
        pop = 1 + 0.06 * max(0, 1 - abs(t - 5.0) / 0.25) if t > 4.7 else 1
        fn = font(int(f_num.size * pop)) if pop > 1.001 else f_num
        d.text((W / 2, H * 0.45), f"{cur:,}{suffix}".replace(",", " "), font=fn, fill=WHITE, anchor="mm")
        if t > 1.6:
            b = min(1, (t - 1.6) / 0.6)
            centered(d, [l.upper() for l in below], f_below, H * 0.60, 92, fill=(int(200 * b),) * 3)
        if t > 6.8:
            c = min(1, (t - 6.8) / 0.6)
            centered(d, [l.upper() for l in final], f_final, H * 0.78, 104, fill=(int(240 * c),) * 3)
        img.save(f"{tmp}/{n + 1:04d}.jpg", quality=90)
    encode(tmp, music, seconds, out)
