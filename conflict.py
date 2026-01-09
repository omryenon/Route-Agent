# app/conflict.py
from typing import List, Dict, Any, Tuple
from shapely.geometry import LineString
from pyproj import Transformer

# lon/lat -> UTM meters (EPSG:32636)
to_m = Transformer.from_crs("EPSG:4326", "EPSG:32636", always_xy=True)

def overlap_area_m2(path_a: List[Dict[str, float]],
                    path_b: List[Dict[str, float]],
                    safety_radius_m: float = 15.0) -> float:
    if not path_a or len(path_a) < 2 or not path_b or len(path_b) < 2:
        return 0.0

    a_pts = [to_m.transform(p["lng"], p["lat"]) for p in path_a]
    b_pts = [to_m.transform(p["lng"], p["lat"]) for p in path_b]

    a_corr = LineString(a_pts).buffer(safety_radius_m)
    b_corr = LineString(b_pts).buffer(safety_radius_m)

    inter = a_corr.intersection(b_corr)
    return float(inter.area) if not inter.is_empty else 0.0

def _line_meters(path: List[Dict[str, float]]) -> LineString:
    pts = []
    for p in path:
        x, y = to_m.transform(p["lng"], p["lat"])
        pts.append((x, y))
    return LineString(pts)

def detect_conflicts(
    routes: Dict[str, List[Dict[str, float]]],
    safety_radius_m: float = 15.0,
    area_threshold_m2: float = 5.0,
) -> List[Dict[str, Any]]:
    """
    מחזיר רשימת קונפליקטים בין כל זוג כתובות.
    """
    ids = [k for k, v in routes.items() if len(v) >= 2]
    corridors = {}
    for rid in ids:
        line = _line_meters(routes[rid])
        corridors[rid] = line.buffer(safety_radius_m)  # במטרים

    alerts = []
    for i in range(len(ids)):
        for j in range(i+1, len(ids)):
            a, b = ids[i], ids[j]
            inter = corridors[a].intersection(corridors[b])
            if inter.is_empty:
                continue
            area = float(inter.area)  # m^2
            if area < area_threshold_m2:
                continue

            minx, miny, maxx, maxy = inter.bounds
            alerts.append({
                "type": "ROUTE_CONFLICT",
                "a": a,
                "b": b,
                "overlap_area_m2": area,
                "severity": "high" if area > 50 else "medium",
                "bounds_utm": {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy},
                "recommendation": "RECOMPUTE_ROUTE" if area > 50 else "ALERT_ONLY"
            })
    alerts.sort(key=lambda x: x["overlap_area_m2"], reverse=True)
    return alerts
