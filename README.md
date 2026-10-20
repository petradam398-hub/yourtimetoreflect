# yourtimetoreflect

Daily quote posts for @yourtimetoreflect.

    python3 make_post.py "QUOTE" posts/YYYY-MM-DD.png backgrounds/<name>.jpg

- `backgrounds/` - photos to rotate through (dark/moody only; white text without shadow needs a dark area).
- `backgrounds_used.txt` - `date background` log; don't reuse a background used in the last 5 posts.
- `quotes_used.txt` - every quote already posted.
- make_post.py keeps the styling fixed (white bold caps, no full stop) and only moves the text block to the darkest corner of the photo.
