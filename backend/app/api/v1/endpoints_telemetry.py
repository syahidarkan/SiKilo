from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.telemetry import TelemetryPayload, TelemetryResponse
from app.nilm.event_detector import EventDetector, TelemetrySample
from app.nilm.classifier import NILMClassifier

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])

# Per-device state: satu EventDetector + NILMClassifier per device_id
_detectors: dict[str, EventDetector] = {}
_classifier = NILMClassifier()


def _get_detector(device_id: str) -> EventDetector:
    if device_id not in _detectors:
        _detectors[device_id] = EventDetector()
    return _detectors[device_id]


@router.post("/ingest", response_model=TelemetryResponse, status_code=status.HTTP_200_OK)
async def ingest_telemetry(payload: TelemetryPayload) -> TelemetryResponse:
    """
    Terima data telemetri dari ESP32, jalankan NILM event detector,
    dan kembalikan status klasifikasi mesin yang terdeteksi.
    """
    detector = _get_detector(payload.device_id)

    sample = TelemetrySample(
        timestamp=payload.timestamp,
        p_active=payload.p_active,
        q_reactive=payload.q_reactive,
        v_rms=payload.v_rms,
        i_rms=payload.i_rms,
        frequency=payload.frequency,
    )

    event = detector.push(sample)

    if event is None:
        return TelemetryResponse(
            device_id=payload.device_id,
            timestamp=payload.timestamp,
            p_active=payload.p_active,
            detected_event=False,
            message="OK – no transient detected",
        )

    result = _classifier.predict(event)

    return TelemetryResponse(
        device_id=payload.device_id,
        timestamp=payload.timestamp,
        p_active=payload.p_active,
        detected_event=True,
        appliance_class=result.appliance_class,
        appliance_label=result.label,
        confidence=round(result.confidence, 3),
        message=f"Event {event.event_type}: {result.label} (ΔP={event.delta_p:+.1f}W, source={result.source})",
    )
