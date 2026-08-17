"""Coordinate parsing and geodesic geometry for AIXM output.

The geodesic buffer (not a planar/Euclidean one) matters: a NOTAM radius is
defined in nautical miles over the Earth's surface, and a naive lat/lon
buffer distorts badly away from the equator. This projects to a local
azimuthal equidistant plane centred on the point, buffers there, and
projects back -- accurate for the metre-scale a NOTAM circle needs.
"""

import re
from dataclasses import dataclass

from pyproj import CRS, Transformer
from shapely.geometry import Point, Polygon
from shapely.ops import transform as shapely_transform

_COORDINATES_PATTERN = re.compile(r"^(\d{2})(\d{2})([NS])(\d{3})(\d{2})([EW])(\d{3})$")
_NAUTICAL_MILE_M = 1852.0


@dataclass(frozen=True)
class ParsedCoordinates:
    latitude: float
    longitude: float
    radius_nm: int


def parse_coordinates_radius(value: str) -> ParsedCoordinates:
    """Parses the QLineInput.coordinates_radius wire format
    (DDMM[NS]DDDMM[EW]RRR, e.g. "0536N00010W005") into decimal degrees."""
    match = _COORDINATES_PATTERN.match(value)
    if not match:
        raise ValueError(f"Coordinates/radius '{value}' does not match the expected grammar")
    lat_deg, lat_min, lat_hem, lon_deg, lon_min, lon_hem, radius = match.groups()
    latitude = int(lat_deg) + int(lat_min) / 60.0
    if lat_hem == "S":
        latitude = -latitude
    longitude = int(lon_deg) + int(lon_min) / 60.0
    if lon_hem == "W":
        longitude = -longitude
    return ParsedCoordinates(latitude=latitude, longitude=longitude, radius_nm=int(radius))


def geodesic_circle(latitude: float, longitude: float, radius_nm: float, segments: int = 32) -> Polygon:
    """Returns a Polygon (lon, lat order, matching GML posList convention)
    approximating a geodesic circle of `radius_nm` centred on the point."""
    radius_m = radius_nm * _NAUTICAL_MILE_M
    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={latitude} +lon_0={longitude} +x_0=0 +y_0=0 +ellps=WGS84"
    )
    wgs84 = CRS.from_epsg(4326)
    to_local = Transformer.from_crs(wgs84, local_crs, always_xy=True).transform
    to_wgs84 = Transformer.from_crs(local_crs, wgs84, always_xy=True).transform
    center_local = shapely_transform(to_local, Point(longitude, latitude))
    circle_local = center_local.buffer(radius_m, quad_segs=max(segments // 4, 1))
    circle_wgs84 = shapely_transform(to_wgs84, circle_local)
    if not isinstance(circle_wgs84, Polygon):  # pragma: no cover - defensive
        raise ValueError("Geodesic buffer did not produce a polygon")
    return circle_wgs84
