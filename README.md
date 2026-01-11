# Digitarr - Daily Digital Movie Release Checker

A dockerized tool that checks for **daily digital movie releases** and automatically requests them through **Overseerr** or **Riven** with intelligent filtering and Discord notifications.

## 🎬 Features

- 🎬 **Digital Release Detection**: Checks for movies with digital releases today (not theatrical)
- 📡 **Multiple Release Sources**: Use TMDB or dvdsreleasedates.com for release dates
- 🎯 **Multi-Service Support**: Request through Overseerr and/or Riven simultaneously
- 🔔 **Discord Notifications**: Get notified for each movie added with poster and rating
- 🎥 **Smart Filtering**: Filter by TMDB rating, language, genre, MPAA rating, and adult content
- 🐳 **Docker Native**: Complete Docker and Docker Compose setup
- ⚙️ **Fully Configurable**: JSON-based settings + complete environment variable support
- 📅 **Daily Scheduling**: Run at a specific time daily with optional request delay

## 🔑 Prerequisites

- Docker and Docker Compose (or Python 3.11+)
- **TMDB API key** (free from [themoviedb.org](https://www.themoviedb.org/))
- **At least ONE of:**
  - Overseerr instance with API key
  - Riven instance with API key

## 📦 Quick Start

### Docker Compose (Recommended)

1. Clone the repository
2. Edit `docker-compose.yml` with your API keys
3. Run:

```bash
docker-compose up -d
```

### Manual Installation

```bash
pip install -r requirements.txt
python src/main.py
```

## ⚙️ Configuration

Configure via environment variables (Docker) or `settings.json`.

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| **TMDB_API_KEY** | TMDB API key (required) | `your_tmdb_key` |
| OVERSEERR_API_URL | Overseerr URL | `http://overseerr:5055` |
| OVERSEERR_API_KEY | Overseerr API key | `your_overseerr_key` |
| RIVEN_API_URL | Riven URL | `http://riven:8080` |
| RIVEN_API_KEY | Riven API key | `your_riven_key` |
| DISCORD_WEBHOOK_URL | Discord webhook for notifications | `https://discord.com/api/webhooks/...` |
| RELEASE_SOURCE | Where to get release dates: `tmdb` or `dvdsreleasedates` | `tmdb` |
| RUN_TIME | Time to run daily (24h format) | `19:00` |
| REQUEST_DELAY_MINUTES | Minutes to wait before requests | `0` |

#### Release Source Options

| Source | Description |
|--------|-------------|
| `tmdb` | Uses TMDB's digital release dates (default) |
| `dvdsreleasedates` | Scrapes [dvdsreleasedates.com](https://www.dvdsreleasedates.com/digital-releases/) for more accurate US digital release dates, then looks up movie details on TMDB |

### Filter Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| FILTERS_MIN_TMDB_RATING | Minimum TMDB rating (0-10) | `6.0` |
| FILTERS_EXCLUDE_ADULT | Exclude adult content | `true` |
| FILTERS_ALLOWED_LANGUAGES | Comma-separated language codes (see list below) | `en,es,fr` |
| FILTERS_EXCLUDED_GENRES | Comma-separated genres to exclude (see list below) | `Horror,Documentary` |
| FILTERS_EXCLUDED_CERTIFICATIONS | Comma-separated MPAA ratings to skip (e.g., R, PG-13) | `R,NC-17` |

#### Common Language Codes
| Code | Language |
|------|----------|
| `en` | English |
| `es` | Spanish |
| `fr` | French |
| `de` | German |
| `it` | Italian |
| `pt` | Portuguese |
| `ja` | Japanese |
| `ko` | Korean |
| `zh` | Chinese |
| `hi` | Hindi |
| `ru` | Russian |

#### Available Genres
`Action`, `Adventure`, `Animation`, `Comedy`, `Crime`, `Documentary`, `Drama`, `Family`, `Fantasy`, `History`, `Horror`, `Music`, `Mystery`, `Romance`, `Science Fiction`, `TV Movie`, `Thriller`, `War`, `Western`

#### MPAA Ratings (US Certifications)
| Rating | Description |
|--------|-------------|
| `G` | General Audiences - All ages |
| `PG` | Parental Guidance Suggested |
| `PG-13` | Parents Strongly Cautioned - May be inappropriate for children under 13 |
| `R` | Restricted - Under 17 requires parent |
| `NC-17` | Adults Only - No one 17 and under |

### Example docker-compose.yml

```yaml
version: '3.8'
services:
  digitarr:
    image: arrrrrr/digitarr:latest
    container_name: digitarr
    restart: unless-stopped
    environment:
      - TMDB_API_KEY=your_tmdb_api_key
      - OVERSEERR_API_URL=http://overseerr:5055
      - OVERSEERR_API_KEY=your_overseerr_key
      - DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
      - RUN_TIME=19:00
      - FILTERS_MIN_TMDB_RATING=6.0
      - FILTERS_ALLOWED_LANGUAGES=en
      - FILTERS_EXCLUDED_GENRES=Horror
      - FILTERS_EXCLUDED_CERTIFICATIONS=NC-17
      - TZ=America/New_York
    volumes:
      - ./logs:/app/logs
```

### settings.json Format

```json
{
  "tmdb": {
    "api_key": "your_tmdb_api_key"
  },
  "overseerr": {
    "api_url": "http://overseerr:5055",
    "api_key": "your_overseerr_key"
  },
  "riven": {
    "api_url": "http://riven:8083",
    "api_key": "your_riven_key"
  },
  "filters": {
    "min_tmdb_rating": 6.0,
    "exclude_adult": true,
    "allowed_languages": ["en"],
    "excluded_genres": ["Horror", "Documentary"],
    "excluded_certifications": ["R", "NC-17"]
  },
  "run_time": "19:00",
  "request_delay_minutes": 0,
  "discord": {
    "webhook_url": "https://discord.com/api/webhooks/..."
  },
  "logging": {
    "level": "INFO"
  }
}
```

## 🔍 Filter Examples

### English movies only, rating 6+
```bash
FILTERS_ALLOWED_LANGUAGES=en
FILTERS_MIN_TMDB_RATING=6.0
```

### Exclude Horror and R-rated movies
```bash
FILTERS_EXCLUDED_GENRES=Horror
FILTERS_EXCLUDED_CERTIFICATIONS=R,NC-17
```

### Family-friendly movies
```bash
FILTERS_EXCLUDE_ADULT=true
FILTERS_EXCLUDED_CERTIFICATIONS=R,NC-17
FILTERS_EXCLUDED_GENRES=Horror,Thriller
```

## 🔔 Discord Notifications

When enabled, Digitarr sends individual Discord notifications for each movie added:

- 🎬 Movie poster thumbnail
- ⭐ TMDB rating
- 📝 Movie description
- ✅ Services added to (Overseerr/Riven)

## 📊 Supported Services

### Overseerr
- Adds movies to the request list
- No Radarr/Sonarr configuration required in Overseerr
- Automatically skips already requested movies

### Riven
- Adds movies directly via API
- Uses `POST /api/v1/items/add` endpoint

## 🚀 Usage Modes

### Run Once
Leave `RUN_TIME` empty to run once and exit:
```bash
docker-compose run --rm digitarr
```

### Scheduled Daily
Set `RUN_TIME` to run at a specific time daily:
```bash
RUN_TIME=19:00  # Runs daily at 7 PM
```

## 📝 Logs

Logs are written to `digitarr.log` and console:

```bash
docker-compose logs -f digitarr
```

## 🆘 Troubleshooting

### No releases found
- Check TMDB API key is valid
- Digital releases may not exist for today

### Connection refused
- For Docker, use container names or `host.docker.internal` instead of `localhost`

### Overseerr: Already requested
- Movie already in request list (normal, skipped gracefully)

## 📖 Getting API Keys

### TMDB
1. Go to https://www.themoviedb.org/
2. Settings → API → Request API key
3. Copy API key (v3 auth)

### Overseerr
1. Settings → General → API Keys
2. Create and copy key

### Riven
1. Settings → API Key
2. Copy secret token

## 📄 License

MIT - Free for personal or commercial use
