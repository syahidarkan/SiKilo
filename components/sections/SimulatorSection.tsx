'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, Loader2 } from 'lucide-react';
import Reveal from '@/components/Reveal';
import SectionHead from '@/components/SectionHead';
import KiloAvatar from '@/components/KiloAvatar';
import { useCountUp, useGaze, useReducedMotion } from '@/components/hooks';
import { fetchEstimate, type Estimate, type MachineKey } from '@/lib/waskita';

const EXAMPLES = [
  'Bengkel konveksi 5.500 VA dengan 2 mesin potong dan setrika uap',
  'Laundry kiloan 3.500 VA, 3 mesin cuci dan pengering',
  'Toko kelontong 2.200 VA, freezer dan kulkas besar',
  'Bengkel las 11.000 VA, kompresor dan mesin las MIG',
];

const POWER_TAGS = ['2.200 VA', '3.500 VA', '5.500 VA', '11.000 VA'] as const;
const VA: Record<string, number> = { '2.200 VA': 2200, '3.500 VA': 3500, '5.500 VA': 5500, '11.000 VA': 11000 };

const MACHINES: { tag: string; key: MachineKey; keys: RegExp }[] = [
  { tag: 'Setrika uap', key: 'setrika_uap', keys: /setrika|uap|boiler/i },
  { tag: 'Kompresor angin', key: 'kompresor_angin', keys: /kompresor/i },
  { tag: 'Oven pemanas', key: 'oven_pemanas', keys: /oven|pemanas/i },
  { tag: 'Mesin cuci dan pengering', key: 'mesin_cuci_dryer', keys: /mesin cuci|dryer|pengering|laundry/i },
];

/** Reads a plan size and machines out of free text, so the story the owner types actually drives the result. */
/** Merapikan teks dari backend ke ejaan Indonesia: koma desimal dan tanda hubung. */
const idText = (t: string) => t.replace(/(\d)\.(\d)(?!\d)/g, '$1,$2').replace(/ — /g, ', ');

function parseProfile(text: string) {
  const m = text.match(/(\d{1,2})[.,]?(\d{3})\s*va\b/i);
  const va = m ? Number(m[1] + m[2]) : null;
  const power = va
    ? POWER_TAGS.reduce((best, t) => (Math.abs(VA[t] - va) < Math.abs(VA[best] - va) ? t : best), POWER_TAGS[0])
    : null;
  return { power, machines: MACHINES.filter((x) => x.keys.test(text)).map((x) => x.tag) };
}

// Estimasi kasar CADANGAN, hanya dipakai saat backend WASKITA tidak bisa dihubungi.
// Angka utama datang dari tiruan digital backend (POST /api/v1/public/estimate).
const CAPEX_PER_KWP = 10_500_000; // biaya PLTS atap terpasang, Rp per kWp (selaras config backend)
const SAVING_PER_KWP = 445_000; // Rp hemat per bulan per kWp (kasar, tanpa jadwal agen)

function calcOffline(power: string, machines: number) {
  const va = VA[power] ?? 3500;
  const kwp = Math.min(va / 1000, (va / 1000) * 0.65 * (1 + machines * 0.3) * 0.55);
  const hemat = Math.round(kwp * SAVING_PER_KWP);
  const pbp = (kwp * CAPEX_PER_KWP) / (hemat * 12);
  return { kwp, hemat, pbp };
}

type Result = {
  kwp: number;
  hemat: number;
  pbp: number | null;
  capex: number;
  source: 'server' | 'offline';
  estimate?: Estimate;
};

function Num({
  label, sub, badge, accent, value, format, reduced,
}: {
  label: string; sub?: string; badge?: string; accent: string;
  value: number; format: (n: number) => string; reduced: boolean;
}) {
  const shown = useCountUp(value, reduced);
  return (
    <li className="sim-num">
      <span className="l">{label}</span>
      <b style={{ color: accent }} aria-label={format(value)}>{format(shown)}</b>
      {sub && <span className="s">{sub}</span>}
      {badge && (
        <span className="bd">
          <Check size={12} strokeWidth={3} /> {badge}
        </span>
      )}
    </li>
  );
}

export default function SimulatorSection() {
  const reduced = useReducedMotion();
  const sectionRef = useRef<HTMLElement>(null);
  const [text, setText] = useState('');
  const [power, setPower] = useState('');
  const [machines, setMachines] = useState<string[]>([]);
  const [detected, setDetected] = useState(false);
  const [ghostIdx, setGhostIdx] = useState(0);
  const [ghost, setGhost] = useState('');

  useGaze(sectionRef, reduced);

  // Ghost placeholder types and erases the examples until the owner writes something.
  useEffect(() => {
    if (text) return;
    const prompt = EXAMPLES[ghostIdx];
    if (reduced) {
      setGhost(prompt);
      const t = setTimeout(() => setGhostIdx((p) => (p + 1) % EXAMPLES.length), 3500);
      return () => clearTimeout(t);
    }
    let i = 0;
    let t: ReturnType<typeof setTimeout>;
    const type = () => {
      if (i < prompt.length) {
        setGhost(prompt.slice(0, ++i));
        t = setTimeout(type, 48);
      } else {
        t = setTimeout(erase, 2600);
      }
    };
    const erase = () => {
      if (i > 0) {
        setGhost(prompt.slice(0, --i));
        t = setTimeout(erase, 22);
      } else {
        setGhostIdx((p) => (p + 1) % EXAMPLES.length);
      }
    };
    setGhost('');
    type();
    return () => clearTimeout(t);
  }, [ghostIdx, text, reduced]);

  function onText(v: string) {
    setText(v);
    const p = parseProfile(v);
    if (p.power || p.machines.length) {
      if (p.power) setPower(p.power);
      setMachines(p.machines);
      setDetected(true);
    } else {
      setDetected(false);
    }
  }

  const toggleMachine = (m: string) =>
    setMachines((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]));

  const machineKeys = useMemo(
    () => MACHINES.filter((m) => machines.includes(m.tag)).map((m) => m.key),
    [machines],
  );

  // Hitung lewat tiruan digital WASKITA di backend (debounce); cadangan offline bila gagal.
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [loading, setLoading] = useState(false);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    if (!power) {
      setEstimate(null);
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    const t = setTimeout(() => {
      fetchEstimate(VA[power], machineKeys, ctrl.signal)
        .then((e) => {
          setEstimate(e);
          setOffline(false);
        })
        .catch((err) => {
          if (ctrl.signal.aborted) return;
          console.warn('Estimasi WASKITA gagal, memakai estimasi kasar:', err);
          setEstimate(null);
          setOffline(true);
        })
        .finally(() => {
          if (!ctrl.signal.aborted) setLoading(false);
        });
    }, 450);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [power, machineKeys]);

  const result: Result | null = useMemo(() => {
    if (!power) return null;
    const keysNow = [...machineKeys].sort().join(',');
    if (estimate && estimate.connected_power_va === VA[power] && [...estimate.machines].sort().join(',') === keysNow) {
      return {
        kwp: estimate.recommended_kwp ?? 0,
        hemat: estimate.monthly_savings_idr,
        pbp: estimate.payback_years,
        capex: estimate.capex_idr,
        source: 'server',
        estimate,
      };
    }
    if (offline) {
      const r = calcOffline(power, machines.length);
      return { ...r, capex: r.kwp * CAPEX_PER_KWP, source: 'offline' };
    }
    return null;
  }, [power, estimate, offline, machines.length, machineKeys]);

  return (
    <section id="simulator-section" ref={sectionRef} className="sheet-band">
      <div className="sheet-w">
        <SectionHead
          n="02"
          label="Simulator"
          title={<>Berapa kapasitas PLTS yang <span className="hl">pas</span> untuk usaha Anda?</>}
          lead="Ceritakan usaha Anda dengan kata-kata sendiri, atau pilih langsung dari pilihan di bawah. Perkiraannya langsung muncul."
        />

        <Reveal delay={80}>
          <div className="sim-wrap">
            <div className="sim-composer">
              <div className="relative">
                <label htmlFor="sim-text" className="sr-only">Ceritakan usaha Anda</label>
                <textarea
                  id="sim-text"
                  value={text}
                  onChange={(e) => onText(e.target.value)}
                  rows={2}
                  className="sim-field relative z-10"
                />
                {!text && (
                  <span
                    className="absolute top-0 left-0 pointer-events-none select-none"
                    style={{ color: 'var(--metal-light)', font: '500 clamp(1.05rem,1.8vw,1.3rem)/1.45 var(--font-body)' }}
                    aria-hidden="true"
                  >
                    {ghost}
                    <span className="animate-pulse">|</span>
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2 mt-3">
                <span className="sim-lab" style={{ margin: 0 }}>Coba contoh</span>
                {['Konveksi', 'Laundry', 'Kelontong', 'Bengkel las'].map((name, i) => (
                  <button key={name} type="button" className="sim-chip try" onClick={() => onText(EXAMPLES[i])}>
                    {name}
                  </button>
                ))}
                {detected && (
                  <span
                    className="ml-auto inline-flex items-center gap-1 text-xs font-bold"
                    style={{ color: 'var(--eco-dark)', animation: 'sim-pop 0.35s cubic-bezier(0.2,0.9,0.3,1.2) both' }}
                  >
                    <Check size={12} strokeWidth={3} /> Terbaca dari cerita Anda
                  </span>
                )}
              </div>

              <div className="sim-groups">
                <div role="group" aria-label="Daya PLN terpasang">
                  <span className="sim-lab">Daya PLN terpasang</span>
                  <div className="flex flex-wrap gap-2">
                    {POWER_TAGS.map((tag) => {
                      const on = power === tag;
                      return (
                        <button
                          key={tag}
                          type="button"
                          aria-pressed={on}
                          className="sim-chip pw"
                          onClick={() => { setPower(on ? '' : tag); setDetected(false); }}
                        >
                          {tag}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div role="group" aria-label="Mesin fleksibel">
                  <span className="sim-lab">Mesin yang bisa dijadwalkan (opsional)</span>
                  <div className="flex flex-wrap gap-2">
                    {MACHINES.map(({ tag }) => (
                      <button
                        key={tag}
                        type="button"
                        aria-pressed={machines.includes(tag)}
                        className="sim-chip"
                        onClick={() => { toggleMachine(tag); setDetected(false); }}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Reveal>

        {/* Hasil langsung, Si Kilo yang menarasikan */}
        <div aria-live="polite">
          {loading && !result ? (
            <div className="faq-msg faq-rest" style={{ paddingTop: 28 }}>
              <KiloAvatar className="faq-avatar" />
              <p className="inline-flex items-center gap-2">
                <Loader2 size={14} className="animate-spin" /> Si Kilo sedang menghitung dengan tiruan digital WASKITA…
              </p>
            </div>
          ) : result ? (
            <div style={{ animation: 'sim-pop 0.45s cubic-bezier(0.2,0.9,0.3,1.2) both' }}>
              <ul className="sim-nums">
                <Num
                  label="Kapasitas PLTS yang disarankan"
                  sub={
                    result.estimate?.kwp_without_agent && result.estimate.kwp_reduction_pct
                      ? `Tanpa jadwal agen: ${result.estimate.kwp_without_agent.toFixed(1).replace('.', ',')} kWp`
                      : 'Dihitung setelah agen mengatur jadwal mesin'
                  }
                  accent="var(--eco-dark)"
                  value={result.kwp}
                  format={(n) => `${n.toFixed(1).replace('.', ',')} kWp`}
                  reduced={reduced}
                />
                <Num
                  label="Perkiraan hemat per bulan"
                  sub={
                    result.estimate
                      ? `${result.estimate.savings_pct.toFixed(0)}% dari tagihan ±Rp${Math.round(result.estimate.monthly_bill_now_idr).toLocaleString('id-ID')}`
                      : 'Perkiraan kasar (tanpa server)'
                  }
                  accent="var(--solar-dark)"
                  value={result.hemat}
                  format={(n) => `Rp${Math.round(n).toLocaleString('id-ID')}`}
                  reduced={reduced}
                />
                <Num
                  label="Waktu balik modal"
                  sub={result.capex > 0 ? `Investasi ±Rp${(result.capex / 1e6).toLocaleString('id-ID', { maximumFractionDigits: 1 })} juta` : undefined}
                  badge={
                    result.estimate?.kwp_reduction_pct
                      ? `Panel ${result.estimate.kwp_reduction_pct.toFixed(0)}% lebih kecil berkat agen`
                      : undefined
                  }
                  accent="var(--metal-dark)"
                  value={result.pbp ?? 0}
                  format={(n) => (result.pbp != null ? `${n.toFixed(1).replace('.', ',')} tahun` : '-')}
                  reduced={reduced}
                />
              </ul>
              <div className="faq-msg" style={{ paddingTop: 20 }}>
                <KiloAvatar className="faq-avatar" />
                <p>
                  {result.estimate ? (
                    <>
                      {idText(result.estimate.headline)}{' '}
                      <span style={{ color: 'var(--metal-mid)' }}>
                        Dihitung tiruan digital WASKITA (cuaca {result.estimate.pv_source.includes('nasa') ? 'NASA POWER' : 'clear-sky'},
                        tarif {result.estimate.tariff_group}, ekspor ke PLN tidak dihitung) dari profil mesin yang umum. Ini perkiraan, bukan penawaran.
                      </span>
                    </>
                  ) : (
                    <>
                      Untuk {power}
                      {machines.length > 0 ? ` dengan ${machines.length} mesin yang bisa dijadwalkan` : ''}, PLTS sekitar {result.kwp.toFixed(1).replace('.', ',')} kWp.
                      Server WASKITA sedang tidak terjangkau, jadi angka ini hanya perkiraan kasar untuk gambaran awal, bukan penawaran.
                    </>
                  )}
                </p>
              </div>
            </div>
          ) : (
            <div className="faq-msg faq-rest" style={{ paddingTop: 28 }}>
              <KiloAvatar className="faq-avatar" />
              <p>Pilih daya PLN atau tulis cerita Anda, nanti Si Kilo yang menghitung.</p>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes sim-pop {
          from { opacity: 0; transform: translateY(12px) scale(0.98); }
          to   { opacity: 1; transform: none; }
        }
        @media (prefers-reduced-motion: reduce) {
          [style*="sim-pop"] { animation: none !important; }
        }
      `}</style>
    </section>
  );
}
