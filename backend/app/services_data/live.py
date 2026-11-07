"""
Hub siaran live (in-memory, satu proses) untuk WebSocket dashboard.

Setiap pelanggan punya antrean terbatas; bila klien lambat, pesan tertua
dibuang (dashboard hanya butuh data terbaru). Aman dipanggil dari thread lain:
pesan dijadwalkan ke event loop milik pelanggan.

Catatan deploy: hub ini per proses. Bila API dijalankan dengan beberapa
worker, siaran hanya sampai ke klien yang terhubung ke worker yang sama —
pakai satu worker atau ganti dengan Redis pub/sub.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

QUEUE_MAXSIZE = 200


@dataclass(eq=False)
class Subscription:
    id: int
    umkm_id: Optional[int]  # None = semua UMKM (khusus admin)
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=QUEUE_MAXSIZE))
    dropped: int = 0

    def _put(self, message: dict[str, Any]) -> None:
        if self.queue.full():
            try:
                self.queue.get_nowait()
                self.dropped += 1
            except asyncio.QueueEmpty:  # pragma: no cover
                pass
        self.queue.put_nowait(message)


class LiveHub:
    def __init__(self) -> None:
        self._subs: dict[int, Subscription] = {}
        self._ids = itertools.count(1)

    def subscribe(self, umkm_id: Optional[int]) -> Subscription:
        sub = Subscription(id=next(self._ids), umkm_id=umkm_id, loop=asyncio.get_running_loop())
        self._subs[sub.id] = sub
        return sub

    def unsubscribe(self, sub: Optional[Subscription]) -> None:
        if sub is not None:
            self._subs.pop(sub.id, None)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def publish(self, umkm_id: int, message: dict[str, Any]) -> int:
        """Kirim pesan ke semua pelanggan UMKM ini (dan pelanggan 'semua'). Return jumlah penerima."""
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        n = 0
        for sub in list(self._subs.values()):
            if sub.umkm_id is not None and sub.umkm_id != umkm_id:
                continue
            try:
                if sub.loop is current:
                    sub._put(message)
                elif not sub.loop.is_closed():
                    sub.loop.call_soon_threadsafe(sub._put, message)
                else:
                    self._subs.pop(sub.id, None)
                    continue
                n += 1
            except Exception:  # noqa: BLE001
                logger.exception("Gagal menyiarkan ke pelanggan %s", sub.id)
        return n


hub = LiveHub()
