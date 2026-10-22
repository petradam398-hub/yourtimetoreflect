# yourtimetoreflect

Automatic quote posts for Instagram @yourtimetoreflect, published straight through the
Instagram API by GitHub Actions. No server and no Metricool needed.

## Settings - `config.json`

    "times": ["19:00"]          when to post, Prague time; add more times for more posts a day
    "max_posts_per_day": 25     safety cap
    "background_cooldown": 5    a background is not reused within the last N posts
    "enabled": true/false       master switch

Example, three posts a day: `"times": ["08:00", "13:00", "19:00"]`

## Files

- `queue.json` - upcoming posts (quote + caption), used from the top. When it runs out, posting stops and GitHub emails you.
- `publish.py` - takes the next entry, picks a readable background, renders the image, pushes it and publishes it.
- `make_post.py` - image style: white bold caps, no full stop, no colours, no lines; text goes to the darkest corner.
- `backgrounds/` - photos to rotate through (dark/moody only).
- `posted_log.txt`, `quotes_used.txt`, `backgrounds_used.txt` - history, so nothing is posted twice.

## Secrets (repo Settings > Secrets and variables > Actions)

- `IG_ACCESS_TOKEN` - Instagram API token (Instagram Login, permission instagram_business_content_publish)
- `GH_PAT` - fine-grained GitHub token for this repo with "Secrets: read and write", used to renew the Instagram token weekly

## Manual runs (Actions tab > Post to Instagram > Run workflow)

- `dry` - render only, the image is attached to the run as "preview"
- `force` - publish the next post right now
