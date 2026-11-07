import json
import asyncio
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.nilm.event_detector import EventDetector, TelemetrySample
from app.nilm.classifier import NILMClassifier

router = APIRouter(prefix="/ws", tags=["WebSocket"])

_classifier = NILMClassifier()
_active_connections: list[WebSocket] = []


@router.websocket("/telemetry")
async def ws_telemetry(websocket: WebSocket):
    """
    WebSocket endpoint untuk live telemetri ESP32.
    Client kirim JSON payload sensor, server balas dengan hasil NILM real-time.
    """
    await websocket.accept()
    _active_connections.append(websocket)
    detector = EventDetector()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "JSON tidak valid"})
                continue

            sample = TelemetrySample(
                timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
                p_active=float(data.get("p_active", 0)),
                q_reactive=float(data.get("q_reactive", 0)),
                v_rms=float(data.get("v_rms", 220)),
                i_rms=float(data.get("i_rms", 0)),
                frequency=float(data.get("frequency", 50)),
            )

            event = detector.push(sample)
            response = {
                "device_id": data.get("device_id", "unknown"),
                "timestamp": sample.timestamp.isoformat(),
                "p_active": sample.p_active,
                "q_reactive": sample.q_reactive,
                "v_rms": sample.v_rms,
                "frequency": sample.frequency,
                "detected_event": event is not None,
            }

            if event is not None:
                result = _classifier.predict(event)
                response.update({
                    "event_type": event.event_type,
                    "delta_p": round(event.delta_p, 1),
                    "delta_q": round(event.delta_q, 1),
                    "appliance_class": result.appliance_class,
                    "appliance_label": result.label,
                    "confidence": round(result.confidence, 3),
                    "source": result.source,
                })

            await websocket.send_json(response)

    except WebSocketDisconnect:
        _active_connections.remove(websocket)
