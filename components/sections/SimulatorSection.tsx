'use client';

import { useState, useEffect, useRef } from 'react';

const GHOST_PROMPTS = [
  'Contoh: Bengkel Konveksi 5.500 VA dengan 2 mesin potong uap',
  'Contoh: Laundry Kiloan 3.500 VA, 3 mesin cuci + dryer',
  'Contoh: Toko Kelontong 2.200 VA, freezer + kulkas besar',
  'Contoh: Bengkel Las 11.000 VA, kompresor + mesin las MIG',
];

const POWER_TAGS = ['2.200 VA', '3.500 VA', '5.500 VA', '11.000 VA'];
const MACHINE_TAGS = ['Setrika Uap', 'Kompresor Angin', 'Oven Pemanas', 'Mesin Cuci Dryer'];

interface CalcResult {
  plts: string;
  hemat: string;
  pbp: string;
}

function calcResult(power: string, machines: string[]): CalcResult {
  const vaMap: Record<string, number> = { '2.200 VA': 2200, '3.500 VA': 3500, '5.500 VA': 5500, '11.000 VA': 11000 };
  const va = vaMap[power] ?? 3500;
  const machineFactor = 1 + machines.length * 0.3;
  const baseKwp = (va / 1000) * 0.65 * machineFactor;
  const optKwp  = baseKwp * 0.55;
  const hemat   = Math.round(optKwp * 445000);
  const pbp     = +(optKwp * 1_200_000 / (hemat / 12)).toFixed(1);
  return {
    plts: `${optKwp.toFixed(1)} kWp`,
    hemat: `Rp${hemat.toLocaleString('id-ID')} / bulan`,
    pbp:   `${pbp} Tahun`,
  };
}

export default function SimulatorSection() {
  const [inputVal,          setInputVal]          = useState('');
  const [ghostIdx,          setGhostIdx]          = useState(0);
  const [ghostText,         setGhostText]         = useState('');
  const [selectedPower,     setSelectedPower]     = useState('');
  const [selectedMachines,  setSelectedMachines]  = useState<string[]>([]);
  const [result,            setResult]            = useState<CalcResult | null>(null);
  const [calculating,       setCalculating]       = useState(false);
  const ghostTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (inputVal) return;
    let charIdx = 0;
    const prompt = GHOST_PROMPTS[ghostIdx];
    setGhostText('');
    const type = () => {
      if (charIdx < prompt.length) {
        setGhostText(prompt.slice(0, ++charIdx));
        ghostTimerRef.current = setTimeout(type, 48);
      } else {
        ghostTimerRef.current = setTimeout(() => {
          const erase = () => {
            if (charIdx > 0) {
              setGhostText(prompt.slice(0, --charIdx));
              ghostTimerRef.current = setTimeout(erase, 24);
            } else {
              setGhostIdx((p) => (p + 1) % GHOST_PROMPTS.length);
            }
          };
          ghostTimerRef.current = setTimeout(erase, 1200);
        }, 1800);
      }
    };
    type();
    return () => { if (ghostTimerRef.current) clearTimeout(ghostTimerRef.current); };
  }, [ghostIdx, inputVal]);

  function toggleMachine(m: string) {
    setSelectedMachines((prev) =>
      prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m],
    );
  }

  async function handleCalc() {
    if (!selectedPower || calculating) return;
    setCalculating(true);
    await new Promise((r) => setTimeout(r, 700));
    setResult(calcResult(selectedPower, selectedMachines));
    setCalculating(false);
  }

  return (
    <section
      id="simulator-section"
      className="py-24 md:py-32 px-4"
      style={{ background: 'var(--bg-paper)' }}
    >
      <div className="max-w-2xl mx-auto">

        {/* Section eyebrow */}
        <div className="text-center mb-12">
          <span
            className="inline-flex items-center gap-1.5 text-xs font-bold tracking-widest uppercase mb-4 px-3 py-1 rounded-full"
            style={{ background: 'var(--eco-light)', color: 'var(--eco-dark)' }}
          >
            ☀ Simulator Right-Sizing
          </span>
          <h2
            className="text-3xl md:text-4xl font-extrabold leading-tight mb-4"
            style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)', letterSpacing: '-0.03em' }}
          >
            Temukan ukuran PLTS<br className="hidden md:block" /> yang pas untuk usahamu
          </h2>
          <p className="text-sm md:text-base" style={{ color: 'var(--metal-mid)' }}>
            Masukkan profil usaha, pilih mesin berdaya tinggi, dan dapatkan rekomendasi instan.
          </p>
        </div>

        {/* Form card */}
        <div
          className="rounded-3xl overflow-hidden mb-5"
          style={{ background: '#fff', border: '1.5px solid var(--border-soft)', boxShadow: '0 12px 40px -12px rgba(31,41,55,0.10)' }}
        >
          {/* Card header strip */}
          <div
            className="px-6 md:px-8 py-4 flex items-center gap-2"
            style={{ background: 'var(--bg-surface)', borderBottom: '1px solid var(--border-soft)' }}
          >
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--eco-primary)' }} />
            <span className="text-xs font-semibold" style={{ color: 'var(--metal-mid)' }}>Profil Usaha</span>
          </div>

          <div className="px-6 md:px-8 py-6">
            {/* Text input */}
            <div className="relative mb-6">
              <textarea
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                rows={2}
                className="w-full bg-transparent text-base resize-none focus:outline-none"
                style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)' }}
                placeholder=""
              />
              {!inputVal && (
                <span
                  className="absolute top-0 left-0 text-base pointer-events-none select-none"
                  style={{ color: 'var(--metal-light)' }}
                >
                  {ghostText}<span className="animate-pulse">|</span>
                </span>
              )}
              <div className="h-px" style={{ background: 'var(--border-soft)' }} />
            </div>

            {/* Power tags */}
            <div className="mb-5">
              <p className="text-xs font-bold mb-2.5" style={{ color: 'var(--metal-mid)' }}>Daya PLN Terpasang</p>
              <div className="flex flex-wrap gap-2">
                {POWER_TAGS.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => setSelectedPower(tag === selectedPower ? '' : tag)}
                    className="px-3.5 py-1.5 rounded-full text-xs font-semibold border transition-all duration-150"
                    style={{
                      background: selectedPower === tag ? 'var(--solar-primary)' : 'transparent',
                      borderColor: selectedPower === tag ? 'var(--solar-primary)' : 'var(--border-medium)',
                      color: selectedPower === tag ? '#fff' : 'var(--metal-mid)',
                      boxShadow: selectedPower === tag ? '0 2px 8px -2px rgba(255,158,44,0.4)' : 'none',
                    }}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>

            {/* Machine tags */}
            <div className="mb-7">
              <p className="text-xs font-bold mb-2.5" style={{ color: 'var(--metal-mid)' }}>Mesin Fleksibel (opsional)</p>
              <div className="flex flex-wrap gap-2">
                {MACHINE_TAGS.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => toggleMachine(tag)}
                    className="px-3.5 py-1.5 rounded-full text-xs font-semibold border transition-all duration-150"
                    style={{
                      background: selectedMachines.includes(tag) ? 'var(--eco-primary)' : 'transparent',
                      borderColor: selectedMachines.includes(tag) ? 'var(--eco-primary)' : 'var(--border-medium)',
                      color: selectedMachines.includes(tag) ? '#fff' : 'var(--metal-mid)',
                      boxShadow: selectedMachines.includes(tag) ? '0 2px 8px -2px rgba(47,191,113,0.35)' : 'none',
                    }}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>

            {/* Submit — full-width CTA button */}
            <button
              onClick={handleCalc}
              disabled={!selectedPower || calculating}
              className="w-full py-3.5 rounded-2xl font-bold text-sm text-white transition-all duration-150 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              style={{
                background: 'var(--eco-primary)',
                boxShadow: selectedPower ? '0 6px 24px -6px rgba(47,191,113,0.45)' : 'none',
              }}
            >
              {calculating ? (
                <>
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="white" strokeWidth="3" strokeDasharray="30 60" />
                  </svg>
                  Menghitung…
                </>
              ) : (
                <>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M8 12V4M5 7l3-3 3 3" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Hitung Rekomendasi PLTS
                </>
              )}
            </button>
          </div>
        </div>

        {/* Result cards */}
        {result && (
          <div
            className="grid grid-cols-1 md:grid-cols-3 gap-3"
            style={{ animation: 'fadeUp 0.4s ease both' }}
          >
            {[
              {
                label: 'Kapasitas PLTS Optimal',
                value: result.plts,
                sub: 'Lebih efisien dengan AI Dispatcher',
                accent: 'var(--eco-primary)',
                bg: 'var(--eco-light)',
                icon: '☀',
              },
              {
                label: 'Estimasi Hemat / Bulan',
                value: result.hemat,
                sub: 'Penghematan bulanan terukur',
                accent: 'var(--solar-primary)',
                bg: 'var(--solar-light)',
                icon: '⚡',
              },
              {
                label: 'Waktu Balik Modal',
                value: result.pbp,
                sub: undefined,
                badge: 'Layak Pembiayaan Bank',
                accent: 'var(--eco-dark)',
                bg: 'var(--bg-surface)',
                icon: '📋',
              },
            ].map((card) => (
              <div
                key={card.label}
                className="rounded-2xl p-5"
                style={{ background: '#fff', border: '1.5px solid var(--border-soft)', boxShadow: '0 4px 16px -4px rgba(31,41,55,0.06)' }}
              >
                <div className="flex items-center gap-2 mb-3">
                  <div
                    className="w-7 h-7 rounded-lg flex items-center justify-center text-sm"
                    style={{ background: card.bg }}
                  >
                    {card.icon}
                  </div>
                  <p className="text-xs font-semibold" style={{ color: 'var(--metal-mid)' }}>{card.label}</p>
                </div>
                <p
                  className="text-2xl font-extrabold mb-1"
                  style={{ color: card.accent, fontFamily: 'var(--font-mono)', letterSpacing: '-0.02em' }}
                >
                  {card.value}
                </p>
                {card.sub && <p className="text-xs" style={{ color: 'var(--metal-light)' }}>{card.sub}</p>}
                {card.badge && (
                  <span
                    className="inline-flex items-center gap-1 mt-2 text-xs font-bold px-2.5 py-1 rounded-full"
                    style={{ background: 'var(--eco-light)', color: 'var(--eco-dark)' }}
                  >
                    ✓ {card.badge}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <style>{`
        @keyframes fadeUp {
          from { opacity:0; transform:translateY(16px); }
          to   { opacity:1; transform:translateY(0); }
        }
      `}</style>
    </section>
  );
}
