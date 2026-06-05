# Marblehead Tidegram

Starter project for automatically generating a shareable Marblehead, MA tide + weather Instagram post and publishing it through GitHub Pages, with optional Instagram publishing through the Instagram Graph API.

The first version is intentionally simple and Copilot-friendly:

1. Fetch NOAA tide predictions for the Salem Harbor tide station used for Marblehead-area tides.
2. Fetch hourly National Weather Service forecast data for Marblehead.
3. Score beach windows using editable Marblehead beach rules.
4. Build a full-post prompt with the top three beach days, tide context, and hourly weather snapshots.
5. Generate the complete 4:5 Instagram image with OpenAI image generation.
6. Publish `site/latest.jpg`, `site/latest.png`, `site/latest.json`, and `site/index.html` to GitHub Pages.
7. Optionally post the public `latest.jpg` URL to Instagram.

## Project structure

```text
marblehead-tidegram/
  .github/workflows/daily.yml      # GitHub Actions automation
  config/beaches.json              # Beach/tide recommendation rules
  config/settings.json             # Marblehead, NOAA, NWS, image defaults
  scripts/generate.py              # Build the infographic + static site
  scripts/post_instagram.py        # Publish latest.jpg to Instagram Graph API
  src/tidegram/                    # Reusable Python package code
  site/                            # Generated static site output
  requirements.txt
  .env.example
```

## Beach logic included

The starter rules are in `config/beaches.json` and reflect the planning thread:

- **Gas House Beach**
  - High tide: paddle boarding / harbor float.
  - Low tide: walk to Brown's Island.
- **Preston Beach**
  - Avoid high tide.
  - Best when the tide is already out and still going out, or only about an hour after low tide.
- **Devereux Beach**
  - Good at most tide stages.
  - Bathrooms and showers.
  - Parking may cost money in season.

To add more beaches, add another beach object with one or more rules. Each rule is anchored to a tide event:

```json
{
  "event_type": "L",
  "activity": "Low-tide walk / tide pools",
  "start_minutes": -180,
  "end_minutes": 60,
  "base_score": 82,
  "wind_profile": "walk",
  "sun_required": true,
  "note": "Best when the tide is already out and continuing out."
}
```

`event_type` is `L` for low tide or `H` for high tide. `start_minutes` and `end_minutes` define the good window relative to that tide event. For example, `-180` to `60` means from three hours before low tide until one hour after low tide.

The generator can show more than one beach on a day card when another beach is genuinely strong. `config/settings.json` controls that behavior:

- `recommended_window_min_minutes`: minimum recommendation window to try to show.
- `recommended_window_max_minutes`: maximum recommendation window to try to show, currently four hours.
- `preferred_window_start_hour`: earliest local hour to recommend, currently `9`.
- `preferred_window_end_hour`: latest local hour to recommend, currently `21`.
- `max_beach_options_per_day`: total beach options to show on a card, including the primary pick.
- `alternate_beach_min_score`: minimum score for an alternate.
- `alternate_beach_max_score_gap`: maximum score gap from the day winner.
- `alternate_beach_min_overlap_minutes`: minimum overlap with the winner's time window.

This keeps multi-beach days compact: usually one primary beach, plus one close alternate only when conditions line up.

## Data sources

- NOAA CO-OPS Data API: tide predictions with `product=predictions` and `interval=hilo`.
- NWS API: `points/{lat},{lon}` → `forecastHourly`.
- OpenAI Images API: complete Instagram post generation with the configured image model.
- GitHub Pages: static host for the public image URL.
- Instagram Graph API: optional media container + publish flow.

Useful docs:

- OpenAI image generation: https://platform.openai.com/docs/guides/image-generation
- NOAA CO-OPS Data API: https://api.tidesandcurrents.noaa.gov/api/dev
- NWS API docs: https://www.weather.gov/documentation/services-web-api
- GitHub Pages deploy action: https://github.com/actions/deploy-pages
- Instagram platform docs: https://developers.facebook.com/docs/instagram-platform/

## Local setup

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create `.env`

```bash
cp .env.example .env
```

Edit `.env`:

```bash
OPENAI_API_KEY=sk-your-openai-key
NWS_USER_AGENT=marblehead-tidegram/0.1 (you@example.com)
```

The NWS API asks for a descriptive User-Agent. Use your own email/contact string.

### 4. Test with sample recommendation data

This uses sample tide/weather data instead of NOAA/NWS calls, but it still generates the image with OpenAI:

```bash
python scripts/generate.py --sample
```

Open:

```text
site/index.html
```

You should also see:

```text
site/latest.jpg
site/latest.png
site/latest.json
```

### 5. Generate with live data

```bash
python scripts/generate.py
```

This will fetch live tide/weather data, call the OpenAI Images API, and save the finished Instagram image.

### 6. Try different background directions

List the built-in background/art-direction prompts:

```bash
python scripts/generate.py --list-art-directions
```

Generate one image with a specific numbered direction:

```bash
python scripts/generate.py --sample --art-direction 7
```

The default art direction is configured in `config/settings.json` as `default_art_direction`. It is currently set to `4`.

Generate a batch of full OpenAI post trials with different background directions:

```bash
python scripts/generate.py --sample --background-variants 6
```

The batch command writes trial images to `site/assets/` and creates `site/background-trials.html` for quick comparison. Each trial is a full OpenAI image generation call.

To inspect the exact prompt without making an image generation call:

```bash
python scripts/generate.py --sample --print-prompt
```

## GitHub deployment

### 1. Create a GitHub repo

Example:

```bash
git init
git add .
git commit -m "Initial Marblehead Tidegram starter"
git branch -M main
git remote add origin git@github.com:YOUR_GITHUB_USERNAME/marblehead-tidegram.git
git push -u origin main
```

### 2. Enable GitHub Pages from the deploy branch

In the GitHub repo:

1. Go to **Settings → Pages**.
2. Under **Build and deployment**, set **Source** to **Deploy from a branch**.
3. Set **Branch** to `gh-pages` and **Folder** to `/ (root)`.

The workflow generates `site/` on `main`, publishes those generated files to the `gh-pages` branch, and GitHub Pages serves that branch.

### 3. Add repository secrets

Go to **Settings → Secrets and variables → Actions → Secrets** and add:

| Secret | Required? | Purpose |
|---|---:|---|
| `OPENAI_API_KEY` | Yes | Generates the finished Instagram image. |
| `IG_ACCESS_TOKEN` | Only for Instagram | Access token with publishing permissions. |

The workflow reads `OPENAI_API_KEY` and `IG_ACCESS_TOKEN` from secrets so they are masked in Actions logs.

### 4. Add repository variables

Go to **Settings → Secrets and variables → Actions → Variables** and add:

| Variable | Suggested value | Purpose |
|---|---|---|
| `AUTO_POST_TO_INSTAGRAM` | `false` initially | Set to `true` only after manual posting works. |
| `TIMEZONE` | `America/New_York` | Local timezone for dates, tide windows, filenames, and generated metadata. |
| `NWS_USER_AGENT` | `marblehead-tidegram/0.1 (you@example.com)` | NWS API contact string. |
| `IG_USER_ID` | Your IG business account ID | Instagram Professional Account ID. |
| `NOAA_STATION_ID` | `8442645` | Salem Harbor station used for Marblehead-area tides. |
| `LOCATION_LAT` | `42.5051` | Marblehead latitude. |
| `LOCATION_LON` | `-70.8578` | Marblehead longitude. |
| `DAYS_TO_FORECAST` | `5` | Forecast horizon. |
| `IG_GRAPH_API_BASE_URL` | `https://graph.instagram.com` | Instagram API endpoint for Instagram Login tokens. |
| `GRAPH_API_VERSION` | `v23.0` | Meta Graph API version to call. |
| `ALT_TEXT` | `Marblehead tide and weather outlook infographic` | Optional Instagram alt text. |

Use `America/New_York`, not `EST`, so daylight saving time is handled correctly. GitHub Actions cron still uses UTC, but the generator converts dates and recommendations to Marblehead local time.

### 5. Run the workflow manually

1. Go to **Actions → Daily Marblehead Tidegram**.
2. Click **Run workflow**.
3. Leave `post_to_instagram` unchecked for the first run.
4. Wait for the deploy job to finish.
5. Open the GitHub Pages site URL.
6. Confirm `latest.jpg` loads directly in the browser.

Your direct image URL should look like:

```text
https://YOUR_GITHUB_USERNAME.github.io/marblehead-tidegram/latest.jpg
```

The generated site cache-busts `latest.jpg` in `index.html`, and Instagram posting uses the versioned asset path from `latest.json` (for example `assets/tidegram-YYYY-MM-DD-YYYYMMDDHHMMSS.jpg`) so Meta does not fetch a stale mutable image.

When posting, the workflow waits for the versioned image URL to become public on GitHub Pages. Brand-new Pages assets can briefly return `404` right after the `gh-pages` branch updates.

## Instagram setup notes

The script posts through the Instagram Graph API with:

1. `POST /{ig-user-id}/media` with `image_url` and `caption`.
2. Wait/poll briefly.
3. `POST /{ig-user-id}/media_publish` with the returned `creation_id`.

By default, the script uses `https://graph.instagram.com` and sends the token as `Authorization: Bearer ...`, which matches Instagram Login tokens. If you switch to the older Facebook Login/Page-token flow, set `IG_GRAPH_API_BASE_URL=https://graph.facebook.com`.

Before enabling automation, make sure you have:

- An Instagram Professional account.
- A Meta developer app.
- The correct permissions/scopes approved for publishing.
- A working long-lived token.
- A public direct image URL. GitHub Pages should work because `latest.jpg` is a direct static file.

### Dry-run local Instagram test

```bash
DRY_RUN=true python scripts/post_instagram.py \
  --image-url "https://YOUR_GITHUB_USERNAME.github.io/marblehead-tidegram/latest.jpg"
```

This validates that the image URL is reachable and prints the caption without posting.

### Local Instagram credential test

After you have `IG_USER_ID` and `IG_ACCESS_TOKEN` in `.env`, validate the account/token pair without creating a post:

```bash
python scripts/post_instagram.py --validate-credentials
```

If this fails with `OAuthException` code `190`, the access token is missing, malformed, expired, copied with extra text, or is not an Instagram Graph API token for the connected account.

If the token only exists in GitHub Actions secrets, run **Actions → Daily Marblehead Tidegram → Run workflow** and check `validate_instagram_only`. That validates `IG_USER_ID` and `IG_ACCESS_TOKEN` inside GitHub Actions without generating a new image or posting to Instagram.

### Real local Instagram test

After you have credentials in `.env`:

```bash
DRY_RUN=false python scripts/post_instagram.py \
  --image-url "https://YOUR_GITHUB_USERNAME.github.io/marblehead-tidegram/latest.jpg"
```

### Enable scheduled Instagram posting

Only after the manual workflow and local/one-off Instagram publishing work:

1. Set repository variable `AUTO_POST_TO_INSTAGRAM=true`.
2. The scheduled workflow will generate, deploy, then post each day.

The default cron is:

```yaml
cron: "27,57 12-14 * * *"
```

GitHub Actions cron uses UTC. The workflow checks Marblehead local time and only posts at or after 8:27 AM, then writes a `.posted/instagram-YYYY-MM-DD.txt` marker to `gh-pages` after a successful scheduled post. The extra cron times are retries in case GitHub delays or drops one scheduled run; the marker prevents a later retry from intentionally posting twice on the same local date.

## Development ideas for Copilot

Good next improvements:

- Add Fort Beach, Grace Oliver Beach, Riverhead, and Crocker Park rules.
- Use a true tide-height curve instead of high/low events only.
- Add sunrise/sunset calculations.
- Add a safety warning when wind exceeds a paddleboarding threshold.
- Add an approval gate that generates the image daily but posts only when a GitHub issue comment says `approve`.
- Store a history archive page of all generated tidegrams.
- Add tests for `build_recommendations()` with known tide/weather fixtures.

## Troubleshooting

### NWS returns an error

Check that `NWS_USER_AGENT` is set to a real descriptive string with contact information.

### NOAA returns no predictions

Check `NOAA_STATION_ID`. The starter uses `8442645`, Salem, Salem Harbor, MA.

### OpenAI image generation fails

Check `OPENAI_API_KEY`, the configured `openai_full_post_model`, and account/image-generation access. The project always uses OpenAI for the final image.

### Instagram says it cannot fetch the media

Open the exact `latest.jpg` URL in an incognito browser. It must return the raw image, not an HTML preview or redirect chain.

### Instagram media_publish fails

Usually this is one of: wrong IG user ID, token missing publishing permissions, account not configured as Professional/linked correctly, container not ready yet, or the media URL is not publicly fetchable. The script waits for the URL and polls the container, but API permissions still need to be correct.
