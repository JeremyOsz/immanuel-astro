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

## Development

The application uses:
- **FastAPI** for the web framework
- **Pydantic** for data validation
- **immanuel** for astrological calculations
- **uvicorn** as the ASGI server 