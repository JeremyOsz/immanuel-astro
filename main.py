import asyncio
import copy
import datetime
import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from immanuel import charts
from immanuel.classes.serialize import ToJSON
from immanuel.setup import settings
from immanuel.const import chart

# Import configuration
from config import config

# API Key configuration
API_KEY = config.API_KEY
_house_system_lock = asyncio.Lock()
_planet_sign_timeline_cache_lock = asyncio.Lock()
_planet_sign_timeline_cache: Dict[str, Dict[str, Any]] = {}

async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """Verify the API key from the X-API-Key header."""
    if not x_api_key:
        raise HTTPException(
            status_code=401, 
            detail="API key required. Please provide X-API-Key header."
        )
    
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=403, 
            detail="Invalid API key."
        )
    
    return x_api_key
    
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


def resolve_house_system(house_system: Optional[str]) -> int:
    return house_system_map.get((house_system or "whole_sign").lower(), chart.WHOLE_SIGN)

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


class PlanetSignTimelineRequest(BaseModel):
    start_date: datetime.date = Field(...)
    end_date: datetime.date = Field(...)
    planets: List[str] = Field(..., min_length=1, description="Planet names, e.g. ['Jupiter', 'Saturn']")
    latitude: float = Field(...)
    longitude: float = Field(...)
    time: datetime.time = Field(
        default=datetime.time(hour=12, minute=0, second=0),
        description="Time in HH:MM:SS format",
    )
    house_system: Optional[str] = Field("whole_sign", description="House system to use: 'whole_sign' (default) or 'placidus'")
    step_days: int = Field(1, ge=1, description="Sampling step in days")

    @field_validator("planets")
    @classmethod
    def normalize_planets(cls, planets: List[str]) -> List[str]:
        normalized: List[str] = []
        for planet in planets:
            cleaned = " ".join(planet.strip().split())
            if not cleaned:
                continue
            if cleaned.upper() in {"ASC", "MC"}:
                canonical = cleaned.upper()
            else:
                canonical = cleaned.title()
            if canonical not in normalized:
                normalized.append(canonical)

        if not normalized:
            raise ValueError("At least one valid planet is required")

        return normalized

    @model_validator(mode="after")
    def validate_date_range(self) -> "PlanetSignTimelineRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "start_date": "2025-03-12",
                    "end_date": "2026-03-12",
                    "planets": ["Jupiter", "Saturn"],
                    "latitude": 51.5074,
                    "longitude": -0.1278,
                    "time": "12:00:00",
                    "house_system": "whole_sign",
                    "step_days": 1,
                }
            ]
        }
    }


def iter_sample_dates(start_date: datetime.date, end_date: datetime.date, step_days: int) -> List[datetime.date]:
    dates: List[datetime.date] = []
    current = start_date
    step = datetime.timedelta(days=step_days)

    while current <= end_date:
        dates.append(current)
        current += step

    if dates and dates[-1] != end_date:
        dates.append(end_date)

    return dates


def extract_selected_planets(chart_payload: Dict[str, Any], requested_planets: List[str]) -> Dict[str, Dict[str, Any]]:
    objects = chart_payload.get("objects", {})
    object_lookup: Dict[str, Dict[str, Any]] = {}

    for obj in objects.values():
        obj_name = obj.get("name")
        if isinstance(obj_name, str):
            object_lookup[obj_name.lower()] = obj

    selected: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []

    for planet in requested_planets:
        obj = object_lookup.get(planet.lower())
        if obj is None:
            missing.append(planet)
            continue

        sign = obj.get("sign", {}).get("name")
        longitude = obj.get("longitude", {}).get("raw")
        retrograde = (
            obj.get("movement", {}).get("retrograde")
            if isinstance(obj.get("movement"), dict)
            else None
        )
        if retrograde is None:
            retrograde = obj.get("longitude", {}).get("retrograde", False)

        if sign is None or longitude is None:
            raise ValueError(f"Missing required longitude/sign data for '{planet}'")

        selected[planet] = {
            "longitude": float(longitude),
            "sign": str(sign),
            "retrograde": bool(retrograde),
        }

    if missing:
        raise ValueError(f"Unsupported or missing planet names: {', '.join(missing)}")

    return selected


def build_timeline_metadata(
    points: List[Dict[str, Any]],
    planets: List[str],
) -> Tuple[Dict[str, List[Dict[str, str]]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    segments: Dict[str, List[Dict[str, str]]] = {planet: [] for planet in planets}
    ingresses: List[Dict[str, Any]] = []
    retrograde_switches: List[Dict[str, Any]] = []

    for planet in planets:
        previous_sign: Optional[str] = None
        previous_retrograde: Optional[bool] = None
        previous_date: Optional[str] = None
        segment_start_date: Optional[str] = None

        for point in points:
            point_data = point["planets"].get(planet)
            if point_data is None:
                continue

            date_str = point["date"]
            current_sign = point_data["sign"]
            current_retrograde = point_data["retrograde"]

            if previous_sign is None:
                segment_start_date = date_str
            else:
                if current_sign != previous_sign:
                    segments[planet].append(
                        {
                            "start_date": segment_start_date or date_str,
                            "end_date": previous_date or date_str,
                            "sign": previous_sign,
                        }
                    )
                    ingresses.append(
                        {
                            "date": date_str,
                            "planet": planet,
                            "from_sign": previous_sign,
                            "to_sign": current_sign,
                        }
                    )
                    segment_start_date = date_str

                if current_retrograde != previous_retrograde:
                    retrograde_switches.append(
                        {
                            "date": date_str,
                            "planet": planet,
                            "retrograde": current_retrograde,
                        }
                    )

            previous_sign = current_sign
            previous_retrograde = current_retrograde
            previous_date = date_str

        if previous_sign is not None:
            segments[planet].append(
                {
                    "start_date": segment_start_date or previous_date or "",
                    "end_date": previous_date or "",
                    "sign": previous_sign,
                }
            )

    ingresses.sort(key=lambda item: (item["date"], item["planet"]))
    retrograde_switches.sort(key=lambda item: (item["date"], item["planet"]))
    return segments, ingresses, retrograde_switches


def build_timeline_cache_key(payload: PlanetSignTimelineRequest) -> str:
    cache_key_payload = {
        "start_date": payload.start_date.isoformat(),
        "end_date": payload.end_date.isoformat(),
        "planets": payload.planets,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "time": payload.time.isoformat(),
        "house_system": (payload.house_system or "whole_sign").lower(),
        "step_days": payload.step_days,
    }
    return json.dumps(cache_key_payload, sort_keys=True, separators=(",", ":"))


def compute_planet_sign_timeline(payload: PlanetSignTimelineRequest) -> Dict[str, Any]:
    points: List[Dict[str, Any]] = []
    sample_dates = iter_sample_dates(payload.start_date, payload.end_date, payload.step_days)
    time_str = payload.time.strftime("%H:%M:%S")

    for sample_date in sample_dates:
        date_time = f"{sample_date.isoformat()} {time_str}"
        subject = charts.Subject(
            date_time=date_time,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
        timeline_chart = charts.Natal(subject)
        chart_payload = json.loads(ToJSON().encode(timeline_chart))
        selected_planets = extract_selected_planets(chart_payload, payload.planets)
        points.append({"date": sample_date.isoformat(), "planets": selected_planets})

    segments, ingresses, retrograde_switches = build_timeline_metadata(points, payload.planets)

    return {
        "points": points,
        "segments": segments,
        "ingresses": ingresses,
        "retrograde_switches": retrograde_switches,
    }


@app.post("/birth-chart", summary="Generate a Birth Chart")
async def generate_birth_chart(birth_data: BirthData, api_key: str = Depends(verify_api_key)):
    """
    Generates a natal (birth) chart based on the provided date, time, and location.
    """
    try:
        async with _house_system_lock:
            previous_house_system = settings.house_system
            settings.house_system = resolve_house_system(birth_data.house_system)
            try:
                dob = f"{birth_data.date} {birth_data.time}"
                subject = charts.Subject(
                    date_time=dob,
                    latitude=birth_data.latitude,
                    longitude=birth_data.longitude
                )
                natal_chart = charts.Natal(subject)
                return json.loads(ToJSON().encode(natal_chart))
            finally:
                settings.house_system = previous_house_system
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transits", summary="Calculate Transits for a Given Date")
async def get_transits(transit_data: TransitData, api_key: str = Depends(verify_api_key)):
    """
    Calculates the transiting planets for a given date relative to a natal chart.
    """
    try:
        async with _house_system_lock:
            previous_house_system = settings.house_system
            settings.house_system = resolve_house_system(transit_data.house_system)
            try:
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
            finally:
                settings.house_system = previous_house_system
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/planet-sign-timeline", summary="Generate Planet Sign Timeline")
async def get_planet_sign_timeline(
    timeline_data: PlanetSignTimelineRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Computes planetary longitude/sign/retrograde snapshots over a date range and
    returns sign segments, ingress points, and retrograde direction changes.
    """
    cache_key = build_timeline_cache_key(timeline_data)
    async with _planet_sign_timeline_cache_lock:
        cached = _planet_sign_timeline_cache.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)

    try:
        async with _house_system_lock:
            previous_house_system = settings.house_system
            settings.house_system = resolve_house_system(timeline_data.house_system)
            try:
                timeline_response = compute_planet_sign_timeline(timeline_data)
            finally:
                settings.house_system = previous_house_system
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    async with _planet_sign_timeline_cache_lock:
        _planet_sign_timeline_cache[cache_key] = copy.deepcopy(timeline_response)
    return timeline_response

# To run this application locally:
# uvicorn main:app --reload --port 8001
#
# For production (Render):
# uvicorn main:app --host 0.0.0.0 --port $PORT
