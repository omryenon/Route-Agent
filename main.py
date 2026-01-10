# app/main.py
import os, time, threading
from typing import Dict, List, Any, Optional
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import requests

from chain import get_route
from conflict import detect_conflicts, overlap_area_m2

POLL_SECONDS = float(os.getenv("AGENT_POLL_SECONDS", "2.0"))
SAFETY_RADIUS_M = float(os.getenv("AGENT_SAFETY_RADIUS_M", "15.0"))

# כתובות רכבים (אפשר גם לקרוא מ-ENV או מקובץ)
CAR_ADDRS = [a.strip() for a in os.getenv("CAR_ADDRS", "").split(",") if a.strip()]
if not CAR_ADDRS:
    print("[WARN] CAR_ADDRS is empty. Set env CAR_ADDRS=0x...,0x...,0x...,0x...")
CAR_SERVER_MAP_RAW = os.getenv("CAR_SERVER_MAP", "{}")
CAR_SERVER_MAP = json.loads(CAR_SERVER_MAP_RAW)

CANDIDATE_ALGOS = json.loads(os.getenv("CANDIDATE_ALGOS", '["dijkstra","astar","random","combined"]'))
CANDIDATES_USE_CROP = os.getenv("CANDIDATES_USE_CROP", "true").lower() == "true"


app = FastAPI(title="Route Conflict Agent")

_latest_alerts: List[Dict[str, Any]] = []
_subscribers: List[Any] = []
_last_route_fingerprint: Dict[str, str] = {}
_recommendations: Dict[str, Any] = {}


class ConfigUpdate(BaseModel):
    pollSeconds: Optional[float] = None
    safetyRadiusMeters: Optional[float] = None

def _fingerprint(path: List[Dict[str, float]]) -> str:
    # טביעת אצבע פשוטה: start+end+count
    if not path:
        return "empty"
    s = path[0]
    e = path[-1]
    return f'{len(path)}|{s.get("lat")},{s.get("lng")}->{e.get("lat")},{e.get("lng")}'

def _fetch_candidates(server_url: str, start: Dict[str, float], end: Dict[str, float]) -> Dict[str, Any]:
    payload = {
        "start": start,
        "end": end,
        "dangerZones": [],
        "random_runs": 3,
        "algorithms": CANDIDATE_ALGOS,
        "include_on_road": False,
        "use_crop": CANDIDATES_USE_CROP
    }
    r = requests.post(f"{server_url}/route/candidates", json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def _poll_loop():
    global _latest_alerts, _recommendations

    while True:
        try:
            # 1) קרא את המסלולים האחרונים מהבלוקצ'יין
            routes = {}
            for addr in CAR_ADDRS:
                try:
                    routes[addr] = get_route(addr)
                except Exception:
                    routes[addr] = []

            # 2) חישוב alerts גלובליים (כמו שהיה)
            alerts = detect_conflicts(routes, safety_radius_m=SAFETY_RADIUS_M)
            _latest_alerts = alerts

            # push ל-SSE
            for q in list(_subscribers):
                try:
                    q.append(alerts)
                except Exception:
                    pass

            # 3) Event-driven: בדוק איזה רכב שינה מסלול
            for addr, path in routes.items():
                if not path or len(path) < 2:
                    continue

                fp = _fingerprint(path)
                if _last_route_fingerprint.get(addr) == fp:
                    continue  # אין שינוי → דלג

                _last_route_fingerprint[addr] = fp

                # 4) מצא את השרת של הרכב
                server_url = CAR_SERVER_MAP.get(addr)
                if not server_url:
                    _recommendations[addr] = {
                        "type": "ERROR",
                        "message": "No server mapping for car",
                        "car": addr
                    }
                    continue

                start = path[0] # first point in the path
                end = path[-1]  # last point in the path

                # 5) בקש מועמדים מהשרת של הרכב
                try:
                    cand_resp = _fetch_candidates(server_url, start, end)
                    candidates = cand_resp.get("candidates", [])
                except Exception as e:
                    _recommendations[addr] = {
                        "type": "ERROR",
                        "car": addr,
                        "message": f"Failed to fetch candidates: {e}"
                    }
                    continue

                # 6) דרג מועמדים מול המסלולים הקיימים של אחרים
                scored = []
                for c in candidates:
                    cpath = c.get("path", [])
                    if not cpath or len(cpath) < 2:
                        continue

                    conflict_sum = 0.0
                    for other_addr, other_path in routes.items():
                        if other_addr == addr:
                            continue
                        conflict_sum += overlap_area_m2(
                            cpath, other_path, safety_radius_m=SAFETY_RADIUS_M
                        )

                    length_m = float(c.get("metrics", {}).get("length_m", 0.0))

                    # פונקציית מטרה פשוטה וברורה
                    score = conflict_sum + 0.001 * length_m

                    scored.append({
                        "algorithm": c.get("algorithm"),
                        "score": score,
                        "conflict_area_m2": conflict_sum,
                        "length_m": length_m
                    })

                scored.sort(key=lambda x: x["score"])

                best = scored[0] if scored else None

                # 7) שמור המלצה לרכב הזה
                _recommendations[addr] = {
                    "car": addr,
                    "start": start,
                    "end": end,
                    "best": best,
                    "ranking": scored[:5],
                    "server_url": server_url,
                    "timestamp": time.time()
                }
                requests.post(f"{server_url}/agent/recommendation",
                  json=_recommendations[addr], timeout=5)
        except Exception as e:
            _latest_alerts = [{"type": "ERROR", "message": str(e)}]

        time.sleep(POLL_SECONDS)


threading.Thread(target=_poll_loop, daemon=True).start()

@app.get("/alerts")
def get_alerts():
    return {"alerts": _latest_alerts, "count": len(_latest_alerts)}

@app.get("/alerts/stream")
def alerts_stream():
    """
    SSE: הלקוח עושה EventSource ומקבל עדכונים.
    """
    buf = []

    _subscribers.append(buf)

    def gen():
        try:
            last_sent = None
            while True:
                if buf:
                    payload = buf.pop(0)
                    # SSE format
                    yield f"data: {payload}\n\n"
                time.sleep(0.2)
        finally:
            if buf in _subscribers:
                _subscribers.remove(buf)
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.get("/recommendations")
def get_recommendations():
    return {"recommendations": _recommendations, "count": len(_recommendations)}

@app.get("/recommendations/list")
def get_recommendations_list():
    # ממיר את ה-dict לרשימה
    items = list(_recommendations.values())
    # סדר לפי זמן (הכי חדש למעלה)
    items.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return {"items": items, "count": len(items)}

