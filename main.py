import asyncio
import copy
import datetime
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from immanuel import charts
from immanuel.classes.serialize import ToJSON
from immanuel.setup import settings
from immanuel.const import chart
try:
    import redis
except ImportError:  # pragma: no cover - optional dependency for production caching
    redis = None

# Import configuration
from config import config

# API Key configuration
API_KEY = config.API_KEY
_house_system_lock = asyncio.Lock()
_planet_sign_timeline_cache_lock = asyncio.Lock()
_planet_sign_timeline_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_timeline_storage_lock = asyncio.Lock()


def is_vercel_runtime() -> bool:
    return os.getenv("VERCEL") == "1"


def resolve_timeline_db_path() -> str:
    configured_path = os.getenv("TIMELINE_DB_PATH")
    if configured_path:
        return configured_path

    # Vercel's deployment filesystem is read-only. Use /tmp for writable storage.
    if is_vercel_runtime():
        return "/tmp/planet_sign_timeline_cache.sqlite3"

    return "planet_sign_timeline_cache.sqlite3"


TIMELINE_DB_PATH = resolve_timeline_db_path()
REDIS_URL = os.getenv("REDIS_URL")
TIMELINE_RESPONSE_CACHE_TTL_SECONDS = max(
    60, int(os.getenv("TIMELINE_RESPONSE_CACHE_TTL_SECONDS", str(60 * 60 * 24 * 30)))
)
TIMELINE_RESPONSE_CACHE_VERSION = os.getenv("TIMELINE_RESPONSE_CACHE_VERSION", "v2")
TIMELINE_RESPONSE_CACHE_MAX_ITEMS = max(
    50, int(os.getenv("TIMELINE_RESPONSE_CACHE_MAX_ITEMS", "500"))
)
GENERAL_SKY_REFERENCE = {
    "latitude": 0.0,
    "longitude": 0.0,
    "time": datetime.time(hour=12, minute=0, second=0),
    "frame": "general-sky",
}
NON_GENERAL_SKY_POINTS = {"ASC", "MC", "Part Of Fortune", "Vertex"}
DEFAULT_PRECOMPUTE_PLANETS = [
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
]
DEFAULT_PRECOMPUTE_SCOPE = {
    "latitude": GENERAL_SKY_REFERENCE["latitude"],
    "longitude": GENERAL_SKY_REFERENCE["longitude"],
    "time": GENERAL_SKY_REFERENCE["time"],
    "house_system": "whole_sign",
}
_daily_precompute_task: Optional[asyncio.Task] = None
_redis_client = None
_redis_available = redis is not None and bool(REDIS_URL)

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
FULL_CHART_OBJECTS = [
    chart.SUN, chart.MOON, chart.MERCURY, chart.VENUS, chart.MARS, chart.JUPITER, chart.SATURN,
    chart.URANUS, chart.NEPTUNE, chart.PLUTO, chart.NORTH_NODE, chart.LILITH, chart.CHIRON,
    chart.PART_OF_FORTUNE, chart.VERTEX, chart.ASC, chart.MC,
    chart.HOUSE1, chart.HOUSE2, chart.HOUSE3, chart.HOUSE4, chart.HOUSE5, chart.HOUSE6,
    chart.HOUSE7, chart.HOUSE8, chart.HOUSE9, chart.HOUSE10, chart.HOUSE11, chart.HOUSE12
]
settings.objects = FULL_CHART_OBJECTS

# Set whole sign as the default house system
settings.house_system = chart.WHOLE_SIGN

house_system_map = {
    "whole_sign": chart.WHOLE_SIGN,
    "placidus": chart.PLACIDUS,
}

timeline_object_map = {
    "Sun": chart.SUN,
    "Moon": chart.MOON,
    "Mercury": chart.MERCURY,
    "Venus": chart.VENUS,
    "Mars": chart.MARS,
    "Jupiter": chart.JUPITER,
    "Saturn": chart.SATURN,
    "Uranus": chart.URANUS,
    "Neptune": chart.NEPTUNE,
    "Pluto": chart.PLUTO,
    "North Node": chart.NORTH_NODE,
    "Lilith": chart.LILITH,
    "Chiron": chart.CHIRON,
    "Part Of Fortune": chart.PART_OF_FORTUNE,
    "Vertex": chart.VERTEX,
    "ASC": chart.ASC,
    "MC": chart.MC,
}


def resolve_house_system(house_system: Optional[str]) -> int:
    return house_system_map.get((house_system or "whole_sign").lower(), chart.WHOLE_SIGN)


def normalize_house_system_name(house_system: Optional[str]) -> str:
    cleaned = (house_system or "whole_sign").strip().lower()
    return cleaned if cleaned in house_system_map else "whole_sign"


def normalize_coordinate(value: float) -> float:
    # 6dp is more than enough precision for cache-key identity and improves hit-rate.
    return round(float(value), 6)


def get_redis_client():
    global _redis_client
    if not _redis_available:
        return None
    if _redis_client is not None:
        return _redis_client
    _redis_client = redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    return _redis_client


def init_timeline_storage() -> None:
    with sqlite3.connect(TIMELINE_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS planet_sign_timeline_daily (
                scope_key TEXT NOT NULL,
                date TEXT NOT NULL,
                planet TEXT NOT NULL,
                longitude REAL NOT NULL,
                sign TEXT NOT NULL,
                retrograde INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (scope_key, date, planet)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_planet_sign_timeline_scope_date
            ON planet_sign_timeline_daily(scope_key, date)
            """
        )
        conn.commit()


def build_timeline_scope_key(payload: "PlanetSignTimelineRequest") -> str:
    scope_payload = {
        "frame": GENERAL_SKY_REFERENCE["frame"],
        "latitude": GENERAL_SKY_REFERENCE["latitude"],
        "longitude": GENERAL_SKY_REFERENCE["longitude"],
        "time": GENERAL_SKY_REFERENCE["time"].isoformat(),
    }
    return json.dumps(scope_payload, sort_keys=True, separators=(",", ":"))


def read_stored_timeline_points(
    scope_key: str,
    planets: List[str],
    date_strings: List[str],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    if not date_strings or not planets:
        return {}

    start_date = min(date_strings)
    end_date = max(date_strings)
    planet_placeholders = ",".join(["?"] * len(planets))

    with sqlite3.connect(TIMELINE_DB_PATH) as conn:
        rows = conn.execute(
            f"""
            SELECT date, planet, longitude, sign, retrograde
            FROM planet_sign_timeline_daily
            WHERE scope_key = ?
              AND date >= ?
              AND date <= ?
              AND planet IN ({planet_placeholders})
            """,
            [scope_key, start_date, end_date, *planets],
        ).fetchall()

    points: Dict[str, Dict[str, Dict[str, Any]]] = {}
    requested_dates = set(date_strings)
    for date_str, planet, longitude, sign, retrograde in rows:
        if date_str not in requested_dates:
            continue
        points.setdefault(date_str, {})[planet] = {
            "longitude": float(longitude),
            "sign": str(sign),
            "retrograde": bool(retrograde),
        }

    return points


def write_stored_timeline_points(
    scope_key: str,
    computed_points: Dict[str, Dict[str, Dict[str, Any]]],
) -> None:
    rows: List[Tuple[str, str, str, float, str, int, str]] = []
    updated_at = datetime.datetime.utcnow().isoformat(timespec="seconds")

    for date_str, planets in computed_points.items():
        for planet, planet_data in planets.items():
            rows.append(
                (
                    scope_key,
                    date_str,
                    planet,
                    float(planet_data["longitude"]),
                    str(planet_data["sign"]),
                    1 if bool(planet_data["retrograde"]) else 0,
                    updated_at,
                )
            )

    if not rows:
        return

    with sqlite3.connect(TIMELINE_DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO planet_sign_timeline_daily (
                scope_key,
                date,
                planet,
                longitude,
                sign,
                retrograde,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_key, date, planet) DO UPDATE SET
                longitude = excluded.longitude,
                sign = excluded.sign,
                retrograde = excluded.retrograde,
                updated_at = excluded.updated_at
            """,
            rows,
        )
        conn.commit()


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    global _daily_precompute_task
    init_timeline_storage()
    # Long-running background loops are not a good fit for serverless runtimes.
    should_run_daily_task = not is_vercel_runtime()
    if should_run_daily_task and (_daily_precompute_task is None or _daily_precompute_task.done()):
        _daily_precompute_task = asyncio.create_task(daily_precompute_loop())
    try:
        yield
    finally:
        if should_run_daily_task and _daily_precompute_task is not None:
            _daily_precompute_task.cancel()
            try:
                await _daily_precompute_task
            except asyncio.CancelledError:
                pass
            finally:
                _daily_precompute_task = None

app = FastAPI(
    title="Astrology API",
    description="An API to generate birth charts and transits using the immanuel package.",
    version="1.0.0",
    lifespan=app_lifespan,
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
    latitude: float = Field(
        default=0.0,
        ge=-90,
        le=90,
        description="Ignored for general-sky mode; optional for backward compatibility",
    )
    longitude: float = Field(
        default=0.0,
        ge=-180,
        le=180,
        description="Ignored for general-sky mode; optional for backward compatibility",
    )
    time: datetime.time = Field(
        default=datetime.time(hour=12, minute=0, second=0),
        description="Ignored for general-sky mode; kept for backward compatibility",
    )
    house_system: Optional[str] = Field("whole_sign", description="Ignored for general-sky mode; kept for backward compatibility")
    step_days: int = Field(1, ge=1, description="Sampling step in days")

    @field_validator("planets")
    @classmethod
    def normalize_planets(cls, planets: List[str]) -> List[str]:
        normalized: List[str] = []
        seen = set()
        for planet in planets:
            cleaned = " ".join(planet.strip().split())
            if not cleaned:
                continue
            if cleaned.upper() in {"ASC", "MC"}:
                canonical = cleaned.upper()
            else:
                canonical = cleaned.title()
            if canonical not in seen:
                seen.add(canonical)
                normalized.append(canonical)

        if not normalized:
            raise ValueError("At least one valid planet is required")

        invalid_points = [planet for planet in normalized if planet in NON_GENERAL_SKY_POINTS]
        if invalid_points:
            raise ValueError(
                "General sky motion does not support chart points: "
                + ", ".join(invalid_points)
            )

        return normalized

    @model_validator(mode="after")
    def validate_date_range(self) -> "PlanetSignTimelineRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    @field_validator("house_system")
    @classmethod
    def normalize_house_system(cls, house_system: Optional[str]) -> str:
        raw = (house_system or "whole_sign").strip().lower()
        if raw not in house_system_map:
            raise ValueError("house_system must be one of: whole_sign, placidus")
        return raw

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


def build_default_precompute_payload(target_date: datetime.date) -> PlanetSignTimelineRequest:
    return PlanetSignTimelineRequest(
        start_date=target_date,
        end_date=target_date,
        planets=DEFAULT_PRECOMPUTE_PLANETS,
        latitude=DEFAULT_PRECOMPUTE_SCOPE["latitude"],
        longitude=DEFAULT_PRECOMPUTE_SCOPE["longitude"],
        time=DEFAULT_PRECOMPUTE_SCOPE["time"],
        house_system=DEFAULT_PRECOMPUTE_SCOPE["house_system"],
        step_days=1,
    )


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


def resolve_timeline_object_constants(requested_planets: List[str]) -> List[int]:
    object_constants: List[int] = []
    unsupported: List[str] = []

    for planet in requested_planets:
        obj_const = timeline_object_map.get(planet)
        if obj_const is None:
            unsupported.append(planet)
            continue
        object_constants.append(obj_const)

    if unsupported:
        raise ValueError(f"Unsupported or missing planet names: {', '.join(unsupported)}")

    return object_constants


def extract_selected_planets_from_natal(
    natal_chart: charts.Natal,
    requested_planets: List[str],
) -> Dict[str, Dict[str, Any]]:
    object_lookup: Dict[str, Any] = {}
    for obj in natal_chart.objects.values():
        object_lookup[obj.name.lower()] = obj

    selected: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    for planet in requested_planets:
        obj = object_lookup.get(planet.lower())
        if obj is None:
            missing.append(planet)
            continue

        selected[planet] = {
            "longitude": float(obj.longitude.raw),
            "sign": str(obj.sign.name),
            "retrograde": bool(obj.movement.retrograde),
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
        "version": TIMELINE_RESPONSE_CACHE_VERSION,
        "frame": GENERAL_SKY_REFERENCE["frame"],
        "start_date": payload.start_date.isoformat(),
        "end_date": payload.end_date.isoformat(),
        "planets": payload.planets,
        "step_days": payload.step_days,
    }
    return json.dumps(cache_key_payload, sort_keys=True, separators=(",", ":"))


def build_timeline_redis_key(cache_key: str) -> str:
    return f"planet-sign-timeline:{cache_key}"


async def read_timeline_response_from_memory(cache_key: str) -> Optional[Dict[str, Any]]:
    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    async with _planet_sign_timeline_cache_lock:
        cached_entry = _planet_sign_timeline_cache.get(cache_key)
        if cached_entry is None:
            return None
        expires_at_ts, payload = cached_entry
        if now_ts >= expires_at_ts:
            _planet_sign_timeline_cache.pop(cache_key, None)
            return None
        return copy.deepcopy(payload)


async def write_timeline_response_to_memory(cache_key: str, payload: Dict[str, Any]) -> None:
    expires_at_ts = datetime.datetime.now(datetime.timezone.utc).timestamp() + TIMELINE_RESPONSE_CACHE_TTL_SECONDS
    async with _planet_sign_timeline_cache_lock:
        if len(_planet_sign_timeline_cache) >= TIMELINE_RESPONSE_CACHE_MAX_ITEMS:
            oldest_key = min(_planet_sign_timeline_cache.items(), key=lambda item: item[1][0])[0]
            _planet_sign_timeline_cache.pop(oldest_key, None)
        _planet_sign_timeline_cache[cache_key] = (expires_at_ts, copy.deepcopy(payload))


def read_timeline_response_from_redis_sync(cache_key: str) -> Optional[Dict[str, Any]]:
    client = get_redis_client()
    if client is None:
        return None
    raw = client.get(build_timeline_redis_key(cache_key))
    if not raw:
        return None
    return json.loads(raw)


def write_timeline_response_to_redis_sync(cache_key: str, payload: Dict[str, Any]) -> None:
    client = get_redis_client()
    if client is None:
        return
    client.setex(
        build_timeline_redis_key(cache_key),
        TIMELINE_RESPONSE_CACHE_TTL_SECONDS,
        json.dumps(payload, separators=(",", ":")),
    )


async def read_timeline_response_from_redis(cache_key: str) -> Optional[Dict[str, Any]]:
    if not _redis_available:
        return None
    try:
        return await asyncio.to_thread(read_timeline_response_from_redis_sync, cache_key)
    except Exception:
        return None


async def write_timeline_response_to_redis(cache_key: str, payload: Dict[str, Any]) -> None:
    if not _redis_available:
        return
    try:
        await asyncio.to_thread(write_timeline_response_to_redis_sync, cache_key, payload)
    except Exception:
        return


def compute_planet_positions_for_date(
    payload: PlanetSignTimelineRequest,
    sample_date: datetime.date,
) -> Dict[str, Dict[str, Any]]:
    time_str = GENERAL_SKY_REFERENCE["time"].strftime("%H:%M:%S")
    date_time = f"{sample_date.isoformat()} {time_str}"
    subject = charts.Subject(
        date_time=date_time,
        latitude=GENERAL_SKY_REFERENCE["latitude"],
        longitude=GENERAL_SKY_REFERENCE["longitude"],
    )
    timeline_chart = charts.Natal(subject)
    return extract_selected_planets_from_natal(timeline_chart, payload.planets)


def compute_missing_timeline_dates_sync(
    payload: PlanetSignTimelineRequest,
    missing_dates: List[datetime.date],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    computed: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for sample_date in missing_dates:
        computed[sample_date.isoformat()] = compute_planet_positions_for_date(payload, sample_date)
    return computed


async def compute_missing_timeline_dates(
    payload: PlanetSignTimelineRequest,
    missing_dates: List[datetime.date],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    if not missing_dates:
        return {}

    object_constants = resolve_timeline_object_constants(payload.planets)
    async with _house_system_lock:
        previous_objects = settings.objects
        settings.objects = object_constants
        try:
            return await asyncio.to_thread(compute_missing_timeline_dates_sync, payload, missing_dates)
        finally:
            settings.objects = previous_objects


async def build_or_load_timeline_points(payload: PlanetSignTimelineRequest) -> List[Dict[str, Any]]:
    sample_dates = iter_sample_dates(payload.start_date, payload.end_date, payload.step_days)
    date_strings = [sample_date.isoformat() for sample_date in sample_dates]
    scope_key = build_timeline_scope_key(payload)

    stored = await asyncio.to_thread(read_stored_timeline_points, scope_key, payload.planets, date_strings)
    missing_dates = [
        sample_date
        for sample_date in sample_dates
        if any(planet not in stored.get(sample_date.isoformat(), {}) for planet in payload.planets)
    ]

    if missing_dates:
        computed_points = await compute_missing_timeline_dates(payload, missing_dates)
        async with _timeline_storage_lock:
            await asyncio.to_thread(write_stored_timeline_points, scope_key, computed_points)
        for date_str, planets in computed_points.items():
            stored.setdefault(date_str, {}).update(planets)

    points: List[Dict[str, Any]] = []
    for date_str in date_strings:
        date_planets = stored.get(date_str, {})
        missing_planets = [planet for planet in payload.planets if planet not in date_planets]
        if missing_planets:
            raise ValueError(f"Timeline data incomplete for {date_str}: missing {', '.join(missing_planets)}")

        ordered_planets = {planet: date_planets[planet] for planet in payload.planets}
        points.append({"date": date_str, "planets": ordered_planets})

    return points


async def compute_planet_sign_timeline(payload: PlanetSignTimelineRequest) -> Dict[str, Any]:
    points = await build_or_load_timeline_points(payload)
    segments, ingresses, retrograde_switches = build_timeline_metadata(points, payload.planets)
    return {
        "points": points,
        "segments": segments,
        "ingresses": ingresses,
        "retrograde_switches": retrograde_switches,
    }


async def precompute_today_timeline_scope() -> None:
    today = datetime.date.today()
    payload = build_default_precompute_payload(today)
    await compute_planet_sign_timeline(payload)


def seconds_until_next_daily_precompute(now_utc: datetime.datetime) -> float:
    next_day = (now_utc + datetime.timedelta(days=1)).date()
    next_run = datetime.datetime.combine(
        next_day,
        datetime.time(hour=0, minute=5, tzinfo=datetime.timezone.utc),
    )
    return max(60.0, (next_run - now_utc).total_seconds())


async def daily_precompute_loop() -> None:
    while True:
        try:
            await precompute_today_timeline_scope()
        except Exception as exc:
            print(f"Daily timeline precompute failed: {exc}")

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        await asyncio.sleep(seconds_until_next_daily_precompute(now_utc))


@app.post("/birth-chart", summary="Generate a Birth Chart")
async def generate_birth_chart(birth_data: BirthData, api_key: str = Depends(verify_api_key)):
    """
    Generates a natal (birth) chart based on the provided date, time, and location.
    """
    try:
        async with _house_system_lock:
            previous_house_system = settings.house_system
            previous_objects = settings.objects
            settings.house_system = resolve_house_system(birth_data.house_system)
            settings.objects = FULL_CHART_OBJECTS
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
                settings.objects = previous_objects
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
            previous_objects = settings.objects
            settings.house_system = resolve_house_system(transit_data.house_system)
            settings.objects = FULL_CHART_OBJECTS
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
                settings.objects = previous_objects
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
    cached = await read_timeline_response_from_memory(cache_key)
    if cached is not None:
        return cached

    cached = await read_timeline_response_from_redis(cache_key)
    if cached is not None:
        await write_timeline_response_to_memory(cache_key, cached)
        return copy.deepcopy(cached)

    try:
        timeline_response = await compute_planet_sign_timeline(timeline_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    await write_timeline_response_to_memory(cache_key, timeline_response)
    await write_timeline_response_to_redis(cache_key, timeline_response)
    return timeline_response

# To run this application locally:
# uvicorn main:app --reload --port 8001
#
# For production (Render):
# uvicorn main:app --host 0.0.0.0 --port $PORT
