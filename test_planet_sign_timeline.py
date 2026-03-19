import asyncio

import main


def _request_payload():
    return {
        "start_date": "2025-03-12",
        "end_date": "2025-03-14",
        "planets": ["Jupiter", "Saturn"],
        "latitude": 51.5074,
        "longitude": -0.1278,
        "time": "12:00:00",
        "house_system": "whole_sign",
        "step_days": 1,
    }


def test_planet_sign_timeline_uses_cache(monkeypatch):
    call_count = {"count": 0}
    response_payload = {
        "points": [
            {
                "date": "2025-03-12",
                "planets": {
                    "Jupiter": {"longitude": 12.3, "sign": "Aries", "retrograde": False},
                    "Saturn": {"longitude": 314.2, "sign": "Aquarius", "retrograde": False},
                },
            }
        ],
        "segments": {
            "Jupiter": [{"start_date": "2025-03-12", "end_date": "2025-03-12", "sign": "Aries"}],
            "Saturn": [{"start_date": "2025-03-12", "end_date": "2025-03-12", "sign": "Aquarius"}],
        },
        "ingresses": [],
        "retrograde_switches": [],
    }

    async def _fake_compute(payload):
        call_count["count"] += 1
        return response_payload

    monkeypatch.setattr(main, "compute_planet_sign_timeline", _fake_compute)
    main._planet_sign_timeline_cache.clear()
    payload = main.PlanetSignTimelineRequest(**_request_payload())

    first = asyncio.run(main.get_planet_sign_timeline(payload, api_key=main.API_KEY))
    second = asyncio.run(main.get_planet_sign_timeline(payload, api_key=main.API_KEY))

    assert first == response_payload
    assert second == response_payload
    assert call_count["count"] == 1


def test_planet_sign_timeline_rejects_inverted_date_range():
    body = _request_payload()
    body["start_date"] = "2025-03-15"
    body["end_date"] = "2025-03-14"

    try:
        main.PlanetSignTimelineRequest(**body)
        assert False, "Expected validation error for inverted date range"
    except Exception as exc:
        assert "end_date must be on or after start_date" in str(exc)


def test_planet_sign_timeline_allows_missing_lat_lon_for_general_sky():
    body = _request_payload()
    body.pop("latitude")
    body.pop("longitude")

    payload = main.PlanetSignTimelineRequest(**body)

    assert payload.latitude == 0.0
    assert payload.longitude == 0.0


def test_planet_sign_timeline_defaults_single_missing_coordinate():
    body = _request_payload()
    body.pop("latitude")
    payload = main.PlanetSignTimelineRequest(**body)
    assert payload.latitude == 0.0
    assert payload.longitude == -0.1278

    body = _request_payload()
    body.pop("longitude")
    payload = main.PlanetSignTimelineRequest(**body)
    assert payload.latitude == 51.5074
    assert payload.longitude == 0.0


def test_planet_sign_timeline_still_rejects_out_of_range_coordinates():
    body = _request_payload()
    body["latitude"] = 120

    try:
        main.PlanetSignTimelineRequest(**body)
        assert False, "Expected validation error for out-of-range latitude"
    except Exception as exc:
        assert "less than or equal to 90" in str(exc)


def test_build_timeline_metadata_tracks_ingresses_and_retrograde_switches():
    points = [
        {
            "date": "2025-03-12",
            "planets": {"Jupiter": {"longitude": 29.9, "sign": "Aries", "retrograde": False}},
        },
        {
            "date": "2025-03-13",
            "planets": {"Jupiter": {"longitude": 30.1, "sign": "Taurus", "retrograde": False}},
        },
        {
            "date": "2025-03-14",
            "planets": {"Jupiter": {"longitude": 29.8, "sign": "Taurus", "retrograde": True}},
        },
    ]

    segments, ingresses, retrograde_switches = main.build_timeline_metadata(points, ["Jupiter"])

    assert segments == {
        "Jupiter": [
            {"start_date": "2025-03-12", "end_date": "2025-03-12", "sign": "Aries"},
            {"start_date": "2025-03-13", "end_date": "2025-03-14", "sign": "Taurus"},
        ]
    }
    assert ingresses == [
        {
            "date": "2025-03-13",
            "planet": "Jupiter",
            "from_sign": "Aries",
            "to_sign": "Taurus",
        }
    ]
    assert retrograde_switches == [{"date": "2025-03-14", "planet": "Jupiter", "retrograde": True}]


def test_planet_sign_timeline_route_is_registered():
    routes = [route for route in main.app.routes if route.path == "/planet-sign-timeline"]
    assert len(routes) == 1
    assert "POST" in routes[0].methods


def test_build_or_load_timeline_points_backfills_missing_dates(monkeypatch):
    payload = main.PlanetSignTimelineRequest(**_request_payload())
    writes = {"count": 0}

    def _fake_read(scope_key, planets, date_strings):
        return {
            "2025-03-12": {
                "Jupiter": {"longitude": 10.0, "sign": "Aries", "retrograde": False},
                "Saturn": {"longitude": 300.0, "sign": "Aquarius", "retrograde": False},
            }
        }

    async def _fake_compute_missing(request_payload, missing_dates):
        assert [item.isoformat() for item in missing_dates] == ["2025-03-13", "2025-03-14"]
        return {
            "2025-03-13": {
                "Jupiter": {"longitude": 11.0, "sign": "Aries", "retrograde": False},
                "Saturn": {"longitude": 301.0, "sign": "Aquarius", "retrograde": False},
            },
            "2025-03-14": {
                "Jupiter": {"longitude": 12.0, "sign": "Aries", "retrograde": False},
                "Saturn": {"longitude": 302.0, "sign": "Aquarius", "retrograde": False},
            },
        }

    def _fake_write(scope_key, computed_points):
        writes["count"] += 1
        assert set(computed_points.keys()) == {"2025-03-13", "2025-03-14"}

    monkeypatch.setattr(main, "read_stored_timeline_points", _fake_read)
    monkeypatch.setattr(main, "compute_missing_timeline_dates", _fake_compute_missing)
    monkeypatch.setattr(main, "write_stored_timeline_points", _fake_write)

    points = asyncio.run(main.build_or_load_timeline_points(payload))

    assert len(points) == 3
    assert [item["date"] for item in points] == ["2025-03-12", "2025-03-13", "2025-03-14"]
    assert writes["count"] == 1
