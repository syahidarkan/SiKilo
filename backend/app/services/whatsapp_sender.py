"""
Pengirim pesan WhatsApp WASKITA.

Penyedia dipilih lewat ``settings.whatsapp_provider``:

- ``none``   → tidak mengirim apa pun, status ``skipped`` (default; aman untuk dev/tes).
- ``fonnte`` → ``POST https://api.fonnte.com/send`` (form ``target``, ``message``,
  header ``Authorization: <token>``).
- ``meta``   → WhatsApp Cloud API
  ``POST https://graph.facebook.com/<versi>/<phone_number_id>/messages``
  CATATAN: Meta hanya mengizinkan pesan teks bebas di dalam jendela 24 jam
  sejak pelanggan terakhir mengirim pesan. Pesan inisiatif bisnis di luar
  jendela itu WAJIB memakai *message template* yang sudah disetujui; bila
  tidak, API menolak (mis. kode galat 131047). Pesan terjadwal
  (``scheduled=True``: brief harian, nota mingguan) dikirim sebagai template
  ``settings.whatsapp_meta_template_name`` (bahasa
  ``whatsapp_meta_template_lang``) dengan SATU parameter body berisi ringkasan
  pesan (baris baru diganti " | ", maks. 1024 karakter — aturan parameter
  template Meta). Bila nama template kosong, dikirim sebagai teks biasa
  (hanya berhasil di dalam jendela 24 jam). Lihat ``docs/WHATSAPP.md``.

``send_whatsapp`` tidak pernah melempar exception ke pemanggil; semua galat
dikembalikan sebagai ``SendResult(status="failed", error=...)``.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

FONNTE_URL = "https://api.fonnte.com/send"
META_URL_TEMPLATE = "https://graph.facebook.com/{version}/{phone_number_id}/messages"
META_REENGAGEMENT_CODES = {131047}
MAX_BODY_CHARS = 4096  # batas teks WhatsApp
MAX_TEMPLATE_PARAM_CHARS = 1024  # batas parameter template Meta


def template_param(body: str, limit: int = MAX_TEMPLATE_PARAM_CHARS) -> str:
    """
    Ubah isi pesan menjadi parameter template Meta: tanpa baris baru/tab dan
    tanpa > 4 spasi berturut-turut (ditolak Meta), dipotong ke ``limit``.
    """
    lines = [" ".join(line.split()) for line in str(body).splitlines()]
    text = " | ".join(line for line in lines if line)
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class SendResult:
    status: str  # sent | failed | skipped
    provider: str  # none | fonnte | meta
    error: Optional[str] = None
    message_id: Optional[str] = None
    http_status: Optional[int] = None
    phone: Optional[str] = None


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """
    Normalisasi nomor Indonesia ke format internasional tanpa '+':
    ``0812-3456-7890`` / ``+62 812…`` / ``812…`` → ``62812…``.
    Kembalikan ``None`` bila tidak tampak seperti nomor seluler Indonesia.
    """
    if not phone:
        return None
    digits = re.sub(r"\D", "", str(phone))
    if digits.startswith("0062"):
        digits = digits[2:]
    if digits.startswith("620"):
        digits = "62" + digits[3:]
    elif digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    if not digits.startswith("628"):
        return None
    if not 10 <= len(digits) <= 15:
        return None
    return digits


def _short(text: str, limit: int = 300) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


async def _send_fonnte(client: httpx.AsyncClient, phone: str, body: str) -> SendResult:
    token = settings.whatsapp_api_token.strip()
    if not token:
        return SendResult("failed", "fonnte", "WHATSAPP_API_TOKEN belum diisi", phone=phone)
    resp = await client.post(
        FONNTE_URL,
        headers={"Authorization": token},
        data={"target": phone, "message": body, "countryCode": "62"},
    )
    data = _json(resp)
    ok_flag = isinstance(data, dict) and data.get("status") is True
    if resp.status_code == 200 and ok_flag:
        mid = data.get("id")
        if isinstance(mid, list):
            mid = mid[0] if mid else None
        return SendResult("sent", "fonnte", None, None if mid is None else str(mid), resp.status_code, phone)
    reason = (data or {}).get("reason") if isinstance(data, dict) else None
    return SendResult(
        "failed", "fonnte", _short(f"Fonnte menolak: {reason or resp.text or resp.status_code}"),
        http_status=resp.status_code, phone=phone,
    )


async def _send_meta(client: httpx.AsyncClient, phone: str, body: str, scheduled: bool = False) -> SendResult:
    token = settings.whatsapp_api_token.strip()
    phone_number_id = settings.whatsapp_phone_number_id.strip()
    if not token or not phone_number_id:
        return SendResult(
            "failed", "meta", "WHATSAPP_API_TOKEN dan WHATSAPP_PHONE_NUMBER_ID wajib diisi untuk Meta", phone=phone
        )
    url = META_URL_TEMPLATE.format(version=settings.whatsapp_meta_api_version, phone_number_id=phone_number_id)
    template = settings.whatsapp_meta_template_name.strip()
    if scheduled and template:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": settings.whatsapp_meta_template_lang or "id"},
                "components": [
                    {"type": "body", "parameters": [{"type": "text", "text": template_param(body)}]}
                ],
            },
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
    resp = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
    data = _json(resp)
    if 200 <= resp.status_code < 300 and isinstance(data, dict) and data.get("messages"):
        mid = (data["messages"][0] or {}).get("id")
        return SendResult("sent", "meta", None, mid, resp.status_code, phone)
    err = (data or {}).get("error", {}) if isinstance(data, dict) else {}
    code = err.get("code") if isinstance(err, dict) else None
    msg = err.get("message") if isinstance(err, dict) else None
    text = f"Meta menolak (kode {code}): {msg or resp.text or resp.status_code}"
    if code in META_REENGAGEMENT_CODES:
        text += (
            " — di luar jendela 24 jam; pesan inisiatif bisnis wajib memakai template yang disetujui "
            "(isi WHATSAPP_META_TEMPLATE_NAME)."
        )
    return SendResult("failed", "meta", _short(text), http_status=resp.status_code, phone=phone)


async def send_whatsapp(
    phone: Optional[str],
    body: str,
    *,
    provider: Optional[str] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
    timeout_s: Optional[float] = None,
    scheduled: bool = False,
) -> SendResult:
    """
    Kirim ``body`` ke ``phone`` lewat penyedia yang dikonfigurasi.

    ``scheduled=True`` menandai pesan inisiatif bisnis (brief/nota): untuk Meta
    dikirim sebagai template bila ``whatsapp_meta_template_name`` diisi.

    ``provider`` menimpa ``settings.whatsapp_provider`` (untuk tes);
    ``transport`` memungkinkan ``httpx.MockTransport`` di tes (tanpa jaringan).
    """
    prov = (provider or settings.whatsapp_provider or "none").lower()
    if prov == "none":
        return SendResult("skipped", "none", "WHATSAPP_PROVIDER=none (pengiriman dimatikan)", phone=phone)
    if prov not in ("fonnte", "meta"):
        return SendResult("failed", prov, f"Penyedia WhatsApp tidak dikenal: {prov}", phone=phone)
    target = normalize_phone(phone)
    if target is None:
        return SendResult("failed", prov, f"Nomor WhatsApp tidak valid: {phone!r}", phone=phone)
    text = (body or "").strip()
    if not text:
        return SendResult("failed", prov, "Isi pesan kosong", phone=target)
    if len(text) > MAX_BODY_CHARS:
        text = text[: MAX_BODY_CHARS - 1] + "…"

    timeout = httpx.Timeout(timeout_s if timeout_s is not None else settings.whatsapp_timeout_s)
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            if prov == "fonnte":
                result = await _send_fonnte(client, target, text)
            else:
                result = await _send_meta(client, target, text, scheduled=scheduled)
    except httpx.TimeoutException:
        result = SendResult("failed", prov, "Waktu habis menghubungi penyedia WhatsApp", phone=target)
    except httpx.HTTPError as exc:
        result = SendResult("failed", prov, _short(f"Galat jaringan: {type(exc).__name__}: {exc}"), phone=target)
    except Exception as exc:  # noqa: BLE001 - jangan pernah melempar ke pemanggil
        logger.exception("Pengiriman WhatsApp gagal tak terduga.")
        result = SendResult("failed", prov, _short(f"Galat tak terduga: {type(exc).__name__}"), phone=target)
    if result.status != "sent":
        logger.warning("WhatsApp %s ke %s gagal: %s", prov, _mask(target), result.error)
    return result


def _mask(phone: Optional[str]) -> str:
    if not phone:
        return "-"
    return phone[:4] + "*" * max(0, len(phone) - 7) + phone[-3:]


__all__ = ["SendResult", "normalize_phone", "send_whatsapp", "template_param"]
