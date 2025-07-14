from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from immanuel import charts
from immanuel.classes.serialize import ToJSON
import datetime
import json
from typing import Optional
from immanuel.setup import settings
from immanuel.const import chart

# Set the objects to include all required points, including all 12 house cusps
settings.objects = [
    chart.SUN, chart.MOON, chart.MERCURY, chart.VENUS, chart.MARS, chart.JUPITER, chart.SATURN,
    chart.URANUS, chart.NEPTUNE, chart.PLUTO, chart.NORTH_NODE, chart.LILITH, chart.CHIRON,
    chart.PART_OF_FORTUNE, chart.VERTEX, chart.ASC, chart.MC,
    chart.HOUSE1, chart.HOUSE2, chart.HOUSE3, chart.HOUSE4, chart.HOUSE5, chart.HOUSE6,
    chart.HOUSE7, chart.HOUSE8, chart.HOUSE9, chart.HOUSE10, chart.HOUSE11, chart.HOUSE12
]

# Set whole sign as the default house system
settings.house_system = chart.WHOLE_SIGN

house_system_map = {
    "whole_sign": chart.WHOLE_SIGN,
    "placidus": chart.PLACIDUS,
}

app = FastAPI(
    title="Astrology API",
    description="An API to generate birth charts and transits using the immanuel package.",
    version="1.0.0",
)

@app.get("/", summary="Health Check")
async def health_check():
    """Health check endpoint for Render deployment."""
    return {"status": "healthy", "message": "Astrology API is running"}

class BirthData(BaseModel):
    date: str = Field(...)
    time: str = Field(...)
    place: str = Field(...)
    latitude: float = Field(...)
    longitude: float = Field(...)
    house_system: Optional[str] = Field("whole_sign", description="House system to use: 'whole_sign' (default) or 'placidus'")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "date": "1990-01-01",
                    "time": "12:00:00",
                    "place": "New York, USA",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "house_system": "whole_sign"
                }
            ]
        }
    }

class TransitData(BaseModel):
    natal_date: str = Field(...)
    natal_time: str = Field(...)
    natal_latitude: float = Field(...)
    natal_longitude: float = Field(...)
    transit_date: str = Field(...)
    house_system: Optional[str] = Field("whole_sign", description="House system to use: 'whole_sign' (default) or 'placidus'")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "natal_date": "1990-01-01",
                    "natal_time": "12:00:00",
                    "natal_latitude": 40.7128,
                    "natal_longitude": -74.0060,
                    "transit_date": datetime.date.today().strftime("%Y-%m-%d"),
                    "house_system": "placidus"
                }
            ]
        }
    }

@app.post("/birth-chart", summary="Generate a Birth Chart")
async def generate_birth_chart(birth_data: BirthData):
    """
    Generates a natal (birth) chart based on the provided date, time, and location.
    """
    try:
        # Set house system for this request
        settings.house_system = house_system_map.get(
            (birth_data.house_system or "whole_sign").lower(), chart.WHOLE_SIGN
        )
        dob = f"{birth_data.date} {birth_data.time}"
        subject = charts.Subject(
            date_time=dob,
            latitude=birth_data.latitude,
            longitude=birth_data.longitude
        )
        natal_chart = charts.Natal(subject)
        return json.loads(ToJSON().encode(natal_chart))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transits", summary="Calculate Transits for a Given Date")
async def get_transits(transit_data: TransitData):
    """
    Calculates the transiting planets for a given date relative to a natal chart.
    """
    try:
        # Set house system for this request
        settings.house_system = house_system_map.get(
            (transit_data.house_system or "whole_sign").lower(), chart.WHOLE_SIGN
        )
        natal_dob = f"{transit_data.natal_date} {transit_data.natal_time}"
        natal_subject = charts.Subject(
            date_time=natal_dob,
            latitude=transit_data.natal_latitude,
            longitude=transit_data.natal_longitude
        )
        natal_chart = charts.Natal(natal_subject)

        transit_subject = charts.Subject(
            date_time=f"{transit_data.transit_date} 00:00:00",
            latitude=transit_data.natal_latitude,
            longitude=transit_data.natal_longitude
        )
        transit_chart = charts.Transits(
            latitude=transit_data.natal_latitude,
            longitude=transit_data.natal_longitude,
            aspects_to=natal_chart
        )

        return json.loads(ToJSON().encode(transit_chart))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# To run this application locally:
# uvicorn main:app --reload --port 8001
#
# For production (Render):
# uvicorn main:app --host 0.0.0.0 --port $PORT