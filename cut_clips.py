"""Cut the strongest 8-second parts of a track into music/ clips for reels.
Usage: python3 cut_clips.py TRACK.mp3 NAME [COUNT]
Picks COUNT non-overlapping loud sections (at least 12 s apart, skipping intro/outro),
adds a short fade in/out and normalises loudness so all clips sound equally loud.
"""
import os, subprocess, sys

SECONDS, GAP = 8, 12


def rms_per_quarter_second(path):
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", path, "-af",
         "asetnsamples=11025,astats=metadata=1:reset=1,"
         "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-", "-f", "null", "-"],
        capture_output=True, text=True).stdout
    vals = []
    for line in out.splitlines():
        if "RMS_level=" in line:
            v = line.split("=", 1)[1].strip()
            vals.append(-90.0 if v in ("-inf", "") else float(v))
    return vals


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", path], capture_output=True, text=True).stdout)


def pick(vals, count, total, q=4):
    win = SECONDS * q
    skip = 4 * q  # ignore the very start and end of the track
    last = int((total - SECONDS - 4) * q)  # a clip must end at least 4 s before the track does
    scores = sorted(((sum(10 ** (x / 20) for x in vals[i:i + win]) / win, i / q)
                     for i in range(skip, min(last, len(vals) - win) + 1, q)), reverse=True)
    starts = []
    for _, st in scores:
        if all(abs(st - p) >= GAP for p in starts):
            starts.append(st)
        if len(starts) == count:
            break
    return sorted(starts)


def main(path, name, count=5):
    os.makedirs("music", exist_ok=True)
    made = []
    for n, st in enumerate(pick(rms_per_quarter_second(path), count, duration(path)), 1):
        out = f"music/{name}-{n}.mp3"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(st), "-t", str(SECONDS), "-i", path,
                        "-af", f"afade=t=in:d=0.4,afade=t=out:st={SECONDS - 1.2}:d=1.2,loudnorm=I=-14:TP=-1.5:LRA=11",
                        "-ar", "44100", "-b:a", "192k", out], check=True)
        made.append(f"{out} (from {st:.0f}s)")
    print("\n".join(made))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 5)
