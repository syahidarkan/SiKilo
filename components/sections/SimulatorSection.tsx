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
  const [inputVal,       setInputVal]       = useState('');
  const [ghostIdx,       setGhostIdx]       = useState(0);
  const [ghostText,      setGhostText]      = useState('');
  const [selectedPower,  setSelectedPower]  = useState('');
  const [selectedMachines, setSelectedMachines] = useState<string[]>([]);
  const [result,         setResult]         = useState<CalcResult | null>(null);
  const [calculating,    setCalculating]    = useState(false);
  const ghostTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Ghost typing animation
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
    if (!selectedPower) return;
    setCalculating(true);
    await new Promise((r) => setTimeout(r, 700));
    setResult(calcResult(selectedPower, selectedMachines));
    setCalculating(false);
  }

  return (
    <section
      id="simulator-section"
      className="min-h-screen flex flex-col items-center justify-center px-4 py-20 md:py-28"
      style={{ background: 'var(--bg-paper)' }}
    >
      <div className="max-w-2xl w-full">
        {/* Heading */}
        <div className="text-center mb-10">
          <span className="inline-block text-xs font-bold tracking-widest uppercase mb-3" style={{ color: 'var(--eco-primary)' }}>
            SIMULATOR RIGHT-SIZING
          </span>
          <h2 className="text-3xl md:text-4xl font-bold leading-tight mb-4" style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)' }}>
            Ayo temukan ukuran PLTS<br className="hidden md:block" /> yang cocok untuk usahamu
          </h2>
          <p className="text-sm md:text-base" style={{ color: 'var(--metal-mid)' }}>
            Masukkan profil usaha, pilih mesin berdaya tinggi, dan dapatkan rekomendasi instan.
          </p>
        </div>

        {/* Form card */}
        <div
          className="rounded-3xl p-6 md:p-8 mb-6"
          style={{ background: '#fff', border: '1.5px solid var(--border-soft)', boxShadow: 'var(--shadow-clay)' }}
        >
          {/* Text input */}
          <div className="relative mb-5">
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
                className="absolute top-0 left-0 text-base pointer-events-none"
                style={{ color: 'var(--metal-light)' }}
              >
                {ghostText}
                <span className="animate-pulse">|</span>
              </span>
            )}
            <div className="h-px mt-1" style={{ background: 'var(--border-soft)' }} />
          </div>

          {/* Power tags */}
          <div className="mb-4">
            <p className="text-xs font-semibold mb-2" style={{ color: 'var(--metal-mid)' }}>Daya PLN</p>
            <div className="flex flex-wrap gap-2">
              {POWER_TAGS.map((tag) => (
                <button
                  key={tag}
                  onClick={() => setSelectedPower(tag === selectedPower ? '' : tag)}
                  className="px-3 py-1.5 rounded-full text-xs font-semibold border transition-all"
                  style={{
                    background: selectedPower === tag ? 'var(--solar-primary)' : 'transparent',
                    borderColor: selectedPower === tag ? 'var(--solar-primary)' : 'var(--border-soft)',
                    color: selectedPower === tag ? '#fff' : 'var(--metal-mid)',
                  }}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>

          {/* Machine tags */}
          <div className="mb-6">
            <p className="text-xs font-semibold mb-2" style={{ color: 'var(--metal-mid)' }}>Mesin Fleksibel</p>
            <div className="flex flex-wrap gap-2">
              {MACHINE_TAGS.map((tag) => (
                <button
                  key={tag}
                  onClick={() => toggleMachine(tag)}
                  className="px-3 py-1.5 rounded-full text-xs font-semibold border transition-all"
                  style={{
                    background: selectedMachines.includes(tag) ? 'var(--eco-primary)' : 'transparent',
                    borderColor: selectedMachines.includes(tag) ? 'var(--eco-primary)' : 'var(--border-soft)',
                    color: selectedMachines.includes(tag) ? '#fff' : 'var(--metal-mid)',
                  }}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>

          {/* Submit */}
          <div className="flex justify-end">
            <button
              onClick={handleCalc}
              disabled={!selectedPower || calculating}
              className="w-12 h-12 rounded-full flex items-center justify-center font-bold text-xl text-white transition-all hover:scale-105 active:scale-95 disabled:opacity-40"
              style={{ background: 'var(--eco-primary)', boxShadow: '0 4px 16px -4px rgba(47,191,113,0.4)' }}
              aria-label="Hitung"
            >
              {calculating ? (
                <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="white" strokeWidth="3" strokeDasharray="30 60" />
                </svg>
              ) : '↑'}
            </button>
          </div>
        </div>

        {/* Result cards (appear without reload) */}
        {result && (
          <div
            className="grid grid-cols-1 md:grid-cols-3 gap-4"
            style={{ animation: 'fadeUp 0.4s ease both' }}
          >
            {[
              { label: 'Kapasitas PLTS Optimal', value: result.plts, sub: 'Turun dari estimasi tanpa AI Dispatcher', color: 'var(--eco-primary)' },
              { label: 'Estimasi Hemat Listrik', value: result.hemat, sub: 'Penghematan bulanan terukur', color: 'var(--solar-primary)' },
              { label: 'Waktu Balik Modal (PBP)', value: result.pbp, sub: '', badge: 'Layak Pembiayaan Bank', color: 'var(--metal-dark)' },
            ].map((card) => (
              <div
                key={card.label}
                className="rounded-2xl p-5"
                style={{ background: 'var(--bg-surface)', border: '1.5px solid var(--border-soft)' }}
              >
                <p className="text-xs mb-1" style={{ color: 'var(--metal-light)' }}>{card.label}</p>
                <p className="text-xl font-bold mb-1" style={{ color: card.color, fontFamily: 'var(--font-mono)' }}>
                  {card.value}
                </p>
                {card.sub && <p className="text-xs" style={{ color: 'var(--metal-mid)' }}>{card.sub}</p>}
                {card.badge && (
                  <span
                    className="inline-block mt-2 text-xs font-semibold px-2.5 py-1 rounded-full"
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
