'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Sun, Zap, ClipboardList, Check } from 'lucide-react';
import Reveal from '@/components/Reveal';
import KiloAvatar from '@/components/KiloAvatar';
import { useCountUp, useGaze, useReducedMotion } from '@/components/hooks';

const EXAMPLES = [
  'Bengkel Konveksi 5.500 VA dengan 2 mesin potong uap dan setrika uap',
  'Laundry Kiloan 3.500 VA, 3 mesin cuci + dryer',
  'Toko Kelontong 2.200 VA, freezer + kulkas besar',
  'Bengkel Las 11.000 VA, kompresor + mesin las MIG',
];

const POWER_TAGS = ['2.200 VA', '3.500 VA', '5.500 VA', '11.000 VA'] as const;
const VA: Record<string, number> = { '2.200 VA': 2200, '3.500 VA': 3500, '5.500 VA': 5500, '11.000 VA': 11000 };

const MACHINES: { tag: string; keys: RegExp }[] = [
  { tag: 'Setrika Uap', keys: /setrika|uap|boiler/i },
  { tag: 'Kompresor Angin', keys: /kompresor/i },
  { tag: 'Oven Pemanas', keys: /oven|pemanas/i },
  { tag: 'Mesin Cuci Dryer', keys: /mesin cuci|dryer|laundry/i },
];

/** Reads a plan size and machines out of free text, so the story the owner types actually drives the result. */
function parseProfile(text: string) {
  const m = text.match(/(\d{1,2})[.,]?(\d{3})\s*va\b/i);
  const va = m ? Number(m[1] + m[2]) : null;
  const power = va
    ? POWER_TAGS.reduce((best, t) => (Math.abs(VA[t] - va) < Math.abs(VA[best] - va) ? t : best), POWER_TAGS[0])
    : null;
  return { power, machines: MACHINES.filter((x) => x.keys.test(text)).map((x) => x.tag) };
}

// Placeholder assumptions, to be replaced with real tariff and quotation data.
const CAPEX_PER_KWP = 15_000_000; // rooftop PV installed cost, Rp per kWp
const SAVING_PER_KWP = 445_000; // Rp saved per month per kWp
const SHIFT_GAIN = 0.06; // extra daytime self-consumption per flexible machine the dispatcher can shift

function calc(power: string, machines: number) {
  const va = VA[power] ?? 3500;
  const kwp = (va / 1000) * 0.65 * (1 + machines * 0.3) * 0.55;
  const hemat = Math.round(kwp * SAVING_PER_KWP * (1 + machines * SHIFT_GAIN));
  const pbp = (kwp * CAPEX_PER_KWP) / (hemat * 12);
  return { kwp, hemat, pbp };
}

function Metric({
  label, sub, badge, icon, accent, bg, value, format, reduced,
}: {
  label: string; sub?: string; badge?: string; icon: React.ReactNode; accent: string; bg: string;
  value: number; format: (n: number) => string; reduced: boolean;
}) {
  const shown = useCountUp(value, reduced);
  return (
    <div
      className="rounded-2xl p-5"
      style={{ background: '#fff', border: '1.5px solid var(--border-soft)', boxShadow: '0 4px 16px -4px rgba(31,41,55,0.06)' }}
    >
      <div className="flex items-center gap-2 mb-3">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: bg, color: accent }}>
          {icon}
        </div>
        <p className="text-xs font-semibold" style={{ color: 'var(--metal-mid)' }}>{label}</p>
      </div>
      <p
        className="text-2xl font-extrabold mb-1 tabular-nums"
        style={{ color: accent, fontFamily: 'var(--font-mono)', letterSpacing: '-0.02em' }}
        aria-label={format(value)}
      >
        {format(shown)}
      </p>
      {sub && <p className="text-xs" style={{ color: 'var(--metal-mid)' }}>{sub}</p>}
      {badge && (
        <span
          className="inline-flex items-center gap-1 mt-2 text-xs font-bold px-2.5 py-1 rounded-full"
          style={{ background: 'var(--eco-light)', color: 'var(--eco-dark)' }}
        >
          <Check size={12} strokeWidth={3} /> {badge}
        </span>
      )}
    </div>
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

  const result = useMemo(() => (power ? calc(power, machines.length) : null), [power, machines.length]);

  return (
    <section
      id="simulator-section"
      ref={sectionRef}
      className="py-24 md:py-32 px-4"
      style={{ background: 'var(--bg-paper)' }}
    >
      <div className="max-w-2xl mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <span
              className="inline-flex items-center gap-1.5 text-xs font-bold tracking-widest uppercase mb-4 px-3 py-1 rounded-full"
              style={{ background: 'var(--eco-light)', color: 'var(--eco-dark)' }}
            >
              <Sun size={13} strokeWidth={2.6} /> Simulator Right-Sizing
            </span>
            <h2
              className="text-3xl md:text-4xl font-extrabold leading-tight mb-4"
              style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)', letterSpacing: '-0.03em' }}
            >
              Temukan ukuran PLTS<br className="hidden md:block" /> yang pas untuk usahamu
            </h2>
            <p className="text-sm md:text-base" style={{ color: 'var(--metal-mid)' }}>
              Ceritakan usahamu dengan kata-katamu sendiri, atau pilih langsung. Hasilnya muncul seketika.
            </p>
          </div>
        </Reveal>

        <Reveal delay={80}>
          <div
            className="rounded-3xl overflow-hidden mb-5"
            style={{ background: '#fff', border: '1.5px solid var(--border-soft)', boxShadow: '0 12px 40px -12px rgba(31,41,55,0.10)' }}
          >
            <div
              className="px-6 md:px-8 py-4 flex items-center gap-2"
              style={{ background: 'var(--bg-surface)', borderBottom: '1px solid var(--border-soft)' }}
            >
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--eco-primary)' }} />
              <span className="text-xs font-semibold" style={{ color: 'var(--metal-mid)' }}>Profil Usaha</span>
              {detected && (
                <span
                  className="ml-auto inline-flex items-center gap-1 text-xs font-bold"
                  style={{ color: 'var(--eco-dark)', animation: 'sim-pop 0.35s cubic-bezier(0.2,0.9,0.3,1.2) both' }}
                >
                  <Check size={12} strokeWidth={3} /> Terbaca dari ceritamu
                </span>
              )}
            </div>

            <div className="px-6 md:px-8 py-6">
              <div className="relative mb-4">
                <label htmlFor="sim-text" className="sr-only">Ceritakan usahamu</label>
                <textarea
                  id="sim-text"
                  value={text}
                  onChange={(e) => onText(e.target.value)}
                  rows={2}
                  className="w-full bg-transparent text-base resize-none focus:outline-none relative z-10"
                  style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)' }}
                />
                {!text && (
                  <span
                    className="absolute top-0 left-0 text-base pointer-events-none select-none"
                    style={{ color: 'var(--metal-light)' }}
                    aria-hidden="true"
                  >
                    {ghost}
                    <span className="animate-pulse">|</span>
                  </span>
                )}
                <div className="h-px" style={{ background: 'var(--border-soft)' }} />
              </div>

              {/* Tap-to-fill examples */}
              <div className="flex flex-wrap items-center gap-2 mb-6">
                <span className="text-xs font-bold" style={{ color: 'var(--metal-mid)' }}>Coba contoh:</span>
                {['Konveksi', 'Laundry', 'Kelontong', 'Bengkel Las'].map((name, i) => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => onText(EXAMPLES[i])}
                    className="px-3 py-1 rounded-full text-xs font-semibold transition-transform duration-150 hover:-translate-y-0.5 active:scale-95"
                    style={{ background: 'var(--solar-light)', color: 'var(--solar-dark)' }}
                  >
                    {name}
                  </button>
                ))}
              </div>

              <div className="mb-5">
                <p className="text-xs font-bold mb-2.5" style={{ color: 'var(--metal-mid)' }}>Daya PLN Terpasang</p>
                <div className="flex flex-wrap gap-2" role="group" aria-label="Daya PLN terpasang">
                  {POWER_TAGS.map((tag) => {
                    const on = power === tag;
                    return (
                      <button
                        key={tag}
                        type="button"
                        aria-pressed={on}
                        onClick={() => { setPower(on ? '' : tag); setDetected(false); }}
                        className="px-3.5 py-1.5 rounded-full text-xs font-semibold border transition-all duration-150 active:scale-95"
                        style={{
                          background: on ? 'var(--solar-primary)' : 'transparent',
                          borderColor: on ? 'var(--solar-primary)' : 'var(--border-medium)',
                          color: on ? '#fff' : 'var(--metal-mid)',
                          boxShadow: on ? '0 2px 8px -2px rgba(255,158,44,0.4)' : 'none',
                        }}
                      >
                        {tag}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <p className="text-xs font-bold mb-2.5" style={{ color: 'var(--metal-mid)' }}>Mesin Fleksibel (opsional)</p>
                <div className="flex flex-wrap gap-2" role="group" aria-label="Mesin fleksibel">
                  {MACHINES.map(({ tag }) => {
                    const on = machines.includes(tag);
                    return (
                      <button
                        key={tag}
                        type="button"
                        aria-pressed={on}
                        onClick={() => { toggleMachine(tag); setDetected(false); }}
                        className="px-3.5 py-1.5 rounded-full text-xs font-semibold border transition-all duration-150 active:scale-95"
                        style={{
                          background: on ? 'var(--eco-primary)' : 'transparent',
                          borderColor: on ? 'var(--eco-primary)' : 'var(--border-medium)',
                          color: on ? '#fff' : 'var(--metal-mid)',
                          boxShadow: on ? '0 2px 8px -2px rgba(47,191,113,0.35)' : 'none',
                        }}
                      >
                        {tag}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </Reveal>

        {/* Live result, with Si Kilo narrating */}
        <div aria-live="polite">
          {result ? (
            <div style={{ animation: 'sim-pop 0.45s cubic-bezier(0.2,0.9,0.3,1.2) both' }}>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Metric
                  label="Kapasitas PLTS Optimal"
                  sub="Lebih efisien dengan AI Dispatcher"
                  icon={<Sun size={16} />}
                  accent="var(--eco-primary)"
                  bg="var(--eco-light)"
                  value={result.kwp}
                  format={(n) => `${n.toFixed(1)} kWp`}
                  reduced={reduced}
                />
                <Metric
                  label="Estimasi Hemat / Bulan"
                  sub="Penghematan bulanan terukur"
                  icon={<Zap size={16} />}
                  accent="var(--solar-dark)"
                  bg="var(--solar-light)"
                  value={result.hemat}
                  format={(n) => `Rp${Math.round(n).toLocaleString('id-ID')}`}
                  reduced={reduced}
                />
                <Metric
                  label="Waktu Balik Modal"
                  badge="Layak Pembiayaan Bank"
                  icon={<ClipboardList size={16} />}
                  accent="var(--eco-dark)"
                  bg="var(--bg-surface)"
                  value={result.pbp}
                  format={(n) => `${n.toFixed(1)} Tahun`}
                  reduced={reduced}
                />
              </div>
              <div className="faq-msg" style={{ paddingTop: 16 }}>
                <KiloAvatar className="faq-avatar" />
                <p>
                  Untuk {power}
                  {machines.length > 0 ? ` dengan ${machines.length} mesin fleksibel` : ''}, PLTS sekitar {result.kwp.toFixed(1)} kWp
                  sudah cukup. Ini estimasi kasar untuk gambaran awal, bukan penawaran.
                </p>
              </div>
            </div>
          ) : (
            <div className="faq-msg faq-rest" style={{ paddingTop: 4 }}>
              <KiloAvatar className="faq-avatar" />
              <p>Pilih daya PLN atau tulis ceritamu, nanti Si Kilo yang hitung</p>
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
