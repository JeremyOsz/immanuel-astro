# Deployment Guide for Render

This guide will help you deploy your Astrology API to Render.

## Prerequisites

1. A GitHub account
2. A Render account (free tier available)
3. Your code pushed to a GitHub repository

## Deployment Steps

### 1. Prepare Your Repository

Make sure your repository contains:
- `main.py` - Your FastAPI application
- `requirements.txt` - Python dependencies
- `render.yaml` - Render configuration (optional)
- `Procfile` - Alternative deployment configuration
- `runtime.txt` - Python version specification

### 2. Deploy to Render

#### Option A: Using Render Dashboard

1. Go to [render.com](https://render.com) and sign in
2. Click "New +" and select "Web Service"
3. Connect your GitHub repository
4. Configure the service:
   - **Name**: `astrology-api` (or your preferred name)
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free (or your preferred plan)

#### Option B: Using render.yaml (Blueprints)

1. Push your code with `render.yaml` to GitHub
2. Go to [render.com](https://render.com) and sign in
3. Click "New +" and select "Blueprint"
4. Connect your GitHub repository
5. Render will automatically detect and use your `render.yaml` configuration

### 3. Environment Variables

**Required for API Security:**
1. Go to your service dashboard on Render
2. Navigate to "Environment" tab
3. Add the following environment variable:
   - `API_KEY`: Your secret API key (e.g., "my-super-secret-key-2024")

**Optional:**
- `ENVIRONMENT`: Set to "production" for production deployments
- `HOST`: Host to bind to (default: 0.0.0.0)

**Important:** Never commit your actual API key to version control. Always use environment variables for sensitive data.

### 4. Verify Deployment

Once deployed, your API will be available at:
- `https://your-app-name.onrender.com`
- Health check: `https://your-app-name.onrender.com/`
- API docs: `https://your-app-name.onrender.com/docs`

## Local Development

To run locally:
```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn main:app --reload --port 8001
```

## API Authentication

All API endpoints (except health check) require authentication using an API key.

### Using the API

Include your API key in the request headers:
```bash
curl -X POST "https://your-app-name.onrender.com/birth-chart" \
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

### JavaScript/Fetch Example
```javascript
const response = await fetch('https://your-app-name.onrender.com/birth-chart', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'your-secret-api-key-here'
  },
  body: JSON.stringify({
    date: '1990-01-01',
    time: '12:00:00',
    place: 'New York, USA',
    latitude: 40.7128,
    longitude: -74.0060
  })
});
```

## API Endpoints

- `GET /` - Health check (no authentication required)
- `POST /birth-chart` - Generate birth chart (requires API key)
- `POST /transits` - Calculate transits (requires API key)
- `GET /docs` - Interactive API documentation
- `GET /redoc` - Alternative API documentation

## Troubleshooting

### Common Issues

1. **Build fails**: Check that all dependencies are in `requirements.txt`
2. **Port issues**: Make sure you're using `$PORT` environment variable
3. **Python version**: Ensure `runtime.txt` specifies a supported Python version

### Logs

View deployment logs in the Render dashboard:
1. Go to your service
2. Click on "Logs" tab
3. Check for any error messages

## Support

For Render-specific issues, check the [Render documentation](https://render.com/docs). 