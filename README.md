# Astrology API

A FastAPI application that generates birth charts and calculates transits using the immanuel package.

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   uvicorn main:app --reload
   ```

   The `--reload` flag enables auto-reload during development.

## Usage

Once running, the API will be available at:
- **API Documentation:** http://localhost:8000/docs
- **Alternative Docs:** http://localhost:8000/redoc
- **Base URL:** http://localhost:8000

### Endpoints

- **POST /birth-chart** - Generate a natal birth chart
- **POST /transits** - Calculate transits for a given date

### Example Usage

#### Generate Birth Chart
```bash
curl -X POST "http://localhost:8000/birth-chart" \
  -H "Content-Type: application/json" \
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
curl -X POST "http://localhost:8000/transits" \
  -H "Content-Type: application/json" \
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