"""Sunrise and sunset for the home's position (NOODLE_LAT / NOODLE_LON), from the standard sunrise equation."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

from . import config


def times(day: date | None = None) -> tuple[datetime, datetime] | None:
    """(sunrise, sunset) on a day as local times; None where the sun does not rise or set (polar day/night)."""
    day = day or datetime.now().astimezone().date()
    lat, lon = config.LATITUDE, config.LONGITUDE
    n = math.ceil(day.toordinal() + 1721424.5 - 2451545.0 + 0.0008)
    mean = (n - lon / 360)
    anomaly = math.radians((357.5291 + 0.98560028 * mean) % 360)
    centre = 1.9148 * math.sin(anomaly) + 0.02 * math.sin(2 * anomaly) + 0.0003 * math.sin(3 * anomaly)
    ecliptic = math.radians((math.degrees(anomaly) + centre + 180 + 102.9372) % 360)
    noon = 2451545.0 + mean + 0.0053 * math.sin(anomaly) - 0.0069 * math.sin(2 * ecliptic)
    declination = math.asin(math.sin(ecliptic) * math.sin(math.radians(23.4397)))
    cos_h = (math.sin(math.radians(-0.833)) - math.sin(math.radians(lat)) * math.sin(declination)) / (
        math.cos(math.radians(lat)) * math.cos(declination))
    if not -1 <= cos_h <= 1:
        return None
    half = math.degrees(math.acos(cos_h)) / 360

    def at(jd: float) -> datetime:
        return (datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jd - 2451545.0)).astimezone()

    return at(noon - half), at(noon + half)


def is_dark(now: datetime | None = None) -> bool:
    now = now or datetime.now().astimezone()
    t = times(now.date())
    return not t or not (t[0] <= now < t[1])
