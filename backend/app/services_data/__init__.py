"""
Layanan data lapangan WASKITA: penyimpanan telemetri, buku energi per mesin,
siaran live ke dashboard, ringkasan KPI & rapor.

Modul:
- ``ingest``  — proses sampel telemetri (NILM per perangkat, simpan, ledger).
- ``live``    — hub siaran WebSocket per UMKM.
- ``ledger``  — query & upsert buku energi (EnergyLedger), akses data UMKM.
- ``kpi``     — metrik papan indikator (file evaluasi + DailyPlan + perangkat).
- ``rapor``   — ringkasan kelayakan PLTS (kWp, PBP, skor) dari data ledger.
"""
