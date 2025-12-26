# app/main.py
import os, time, threading
from typing import Dict, List, Any
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from chain import get_route
from conflict import detect_conflicts

POLL_SECONDS = float(os.getenv("AGENT_POLL_SECONDS", "2.0"))
SAFETY_RADIUS_M = float(os.getenv("AGENT_SAFETY_RADIUS_M", "15.0"))

# כתובות רכבים (אפשר גם לקרוא מ-ENV או מקובץ)
CAR_ADDRS = [a.strip() for a in os.getenv("CAR_ADDRS", "").split(",") if a.strip()]
if not CAR_ADDRS:
    print("[WARN] CAR_ADDRS is empty. Set env CAR_ADDRS=0x...,0x...,0x...,0x...")

app = FastAPI(title="Route Conflict Agent")

_latest_alerts: List[Dict[str, Any]] = []
_subscribers: List[Any] = []

class ConfigUpdate(BaseModel):
    pollSeconds: float | None = None
    safetyRadiusMeters: float | None = None

def _poll_loop():
    global _latest_alerts
    while True:
        try:
            routes = {addr: get_route(addr) for addr in CAR_ADDRS}
            alerts = detect_conflicts(routes, safety_radius_m=SAFETY_RADIUS_M)
            _latest_alerts = alerts

            # push ל-SSE
            for q in list(_subscribers):
                try:
                    q.append(alerts)
                except Exception:
                    pass
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
