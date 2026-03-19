# Astrology API

A FastAPI application that generates birth charts and calculates transits using the immanuel package.

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment variables:**
   ```bash
   # Copy the example environment file
   cp env.example .env
   
   # Edit .env and set your API key
   # API_KEY=your-secret-api-key-here
   ```

3. **Run the application:**
   ```bash
   uvicorn main:app --reload --port 8001
   ```

   The `--reload` flag enables auto-reload during development.

## Usage

Once running, the API will be available at:
- **API Documentation:** http://localhost:8001/docs
- **Alternative Docs:** http://localhost:8001/redoc
- **Base URL:** http://localhost:8001
- **Health Check:** http://localhost:8001/ (no authentication required)

### Endpoints

- **POST /birth-chart** - Generate a natal birth chart
- **POST /transits** - Calculate transits for a given date
- **POST /planet-sign-timeline** - Bulk planetary timeline (points, sign segments, ingresses, retrograde switches)

### API Authentication

All endpoints (except health check) require an API key. Include it in the `X-API-Key` header:

### Example Usage

#### Generate Birth Chart
```bash
curl -X POST "http://localhost:8001/birth-chart" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key-here" \
  -d '{
    "date": "1990-01-01",
    "time": "12:00:00",
    "place": "New York, USA",
    "latitude": 40.7128,
    "longitude": -74.0060
  }'
```

#### Calculate Transits
```bash
curl -X POST "http://localhost:8001/transits" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key-here" \
  -d '{
    "natal_date": "1990-01-01",
    "natal_time": "12:00:00",
    "natal_latitude": 40.7128,
    "natal_longitude": -74.0060,
    "transit_date": "2024-01-01"
  }'
```

#### Planet Sign Timeline (Bulk Ephemeris)
```bash
curl -X POST "http://localhost:8001/planet-sign-timeline" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key-here" \
  -d '{
    "start_date": "2025-03-12",
    "end_date": "2026-03-12",
    "planets": ["Jupiter", "Saturn"],
    "latitude": 51.5074,
    "longitude": -0.1278,
    "time": "12:00:00",
    "house_system": "whole_sign",
    "step_days": 1
  }'
```

This endpoint now uses layered caching optimized for long-range ephemeris queries:
- Stores daily planet rows in SQLite keyed by `(latitude, longitude, time, house_system, date, planet)`
- Uses response-level in-memory cache with TTL for hot repeated calls
- Optionally uses shared Redis (`REDIS_URL`) for cross-instance cache hits in serverless
- Backfills only missing dates for each request and persists them
- Runs a daily precompute loop for the default London/noon scope (non-serverless runtimes)

Optional environment variables:
- `TIMELINE_DB_PATH` (default: `planet_sign_timeline_cache.sqlite3`)
- `REDIS_URL` (recommended on Vercel)
- `TIMELINE_RESPONSE_CACHE_TTL_SECONDS` (default: `2592000`)
- `TIMELINE_RESPONSE_CACHE_VERSION` (default: `v1`)
- `TIMELINE_RESPONSE_CACHE_MAX_ITEMS` (default: `500`)

## Development

The application uses:
- **FastAPI** for the web framework
- **Pydantic** for data validation
- **immanuel** for astrological calculations
- **uvicorn** as the ASGI server

## Deploy to Vercel (Serverless)

This repo is now configured for Vercel serverless deployment:
- `api/index.py` exports the FastAPI app for Vercel Functions
- `vercel.json` routes all paths to that function

### Steps

1. Push this repo to GitHub.
2. Import the repo in Vercel.
3. Set environment variable `API_KEY` in Vercel project settings.
4. (Recommended) Set `REDIS_URL` for shared aggressive caching across serverless instances.
5. Deploy.

### Notes for Swiss Ephemeris C bindings

- `immanuel` depends on `pyswisseph` (native extension). Vercel must be able to install a compatible Linux wheel during build.
- If build/runtime fails for `pyswisseph`, keep the frontend on Vercel and run this API on a container/VM service such as Render.
- Without `REDIS_URL`, timeline caching falls back to per-instance memory plus local SQLite (`/tmp` on Vercel), which is less effective across cold starts.
