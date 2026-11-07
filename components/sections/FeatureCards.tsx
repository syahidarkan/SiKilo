'use client';

import { useState, useEffect, useRef } from 'react';

const CARDS = [
  {
    id: '01',
    label: 'Tahu',
    icon: '🔌',
    iconDesc: 'Si Kilo bawa sensor',
    front: 'Kenali setiap mesin yang boros daya, tanpa buka kabel.',
    back: (
      <div className="text-left w-full">
        <p className="text-xs font-bold mb-2" style={{ color: 'var(--eco-primary)' }}>NILM Signal Fingerprint</p>
        <div className="space-y-1.5">
          {[['Kompresor Freezer', 85, '#EF4444'], ['Setrika Uap', 62, '#F97316'], ['Mesin Cuci', 48, '#3B82F6'], ['Lampu LED', 12, '#22C55E']].map(([label, pct, color]) => (
            <div key={String(label)}>
              <div className="flex justify-between text-xs mb-0.5">
                <span style={{ color: 'var(--metal-mid)' }}>{label}</span>
                <span className="font-mono font-bold" style={{ color: color as string }}>{pct}W</span>
              </div>
              <div className="h-1.5 rounded-full" style={{ background: 'var(--border-soft)' }}>
                <div className="h-1.5 rounded-full" style={{ width: `${pct}%`, background: color as string }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    ),
  },
  {
    id: '02',
    label: 'Atur',
    icon: '⏰',
    iconDesc: 'Si Kilo bawa jam',
    front: 'Jadwalkan mesin berat saat matahari sedang paling terik.',
    back: (
      <div className="text-left w-full">
        <p className="text-xs font-bold mb-2" style={{ color: 'var(--solar-primary)' }}>Jadwal AI Hari Ini</p>
        <div className="space-y-1.5">
          {[['08.00–10.00', 'Setrika Uap ON', '#F97316'], ['10.00–14.00', 'Mesin Cuci + Dryer', '#22C55E'], ['14.00–16.00', 'Kompresor Maks', '#3B82F6'], ['17.00+', 'Mode Hemat', '#9CA3AF']].map(([time, act, color]) => (
            <div key={String(time)} className="flex gap-2 items-start">
              <span className="text-xs font-mono shrink-0" style={{ color: color as string }}>{time}</span>
              <span className="text-xs" style={{ color: 'var(--metal-mid)' }}>{act}</span>
            </div>
          ))}
        </div>
      </div>
    ),
  },
  {
    id: '03',
    label: 'Hemat',
    icon: '📱',
    iconDesc: 'Si Kilo bawa HP',
    front: 'Rekomendasi harian langsung di WhatsApp grup kamu.',
    back: (
      <div className="text-left w-full space-y-2">
        <div className="rounded-xl px-3 py-2 text-xs" style={{ background: 'var(--bg-surface)', color: 'var(--metal-dark)' }}>
          <span className="font-bold block mb-0.5" style={{ color: 'var(--eco-primary)' }}>Si Kilo 🤖</span>
          Selamat pagi! Matahari hari ini diprediksi terik 10.00–14.00. Setrika uap & mesin cuci direkomendasikan aktif di jam tersebut 🌞
        </div>
        <div className="rounded-xl px-3 py-2 text-xs" style={{ background: 'var(--bg-surface)', color: 'var(--metal-dark)' }}>
          <span className="font-bold block mb-0.5" style={{ color: 'var(--eco-primary)' }}>Si Kilo 🤖</span>
          Tagihan pekan ini turun 28% vs rata-rata bulan lalu. Hemat Rp340.000 🎉
        </div>
      </div>
    ),
  },
  {
    id: '04',
    label: 'Punya PLTS',
    icon: '📋',
    iconDesc: 'Si Kilo bawa rapor',
    front: 'Dapatkan laporan kelayakan bank dari data energi nyata.',
    back: (
      <div className="text-left w-full">
        <p className="text-xs font-bold mb-2" style={{ color: 'var(--solar-primary)' }}>Energy Credit Scorecard</p>
        <div className="space-y-1.5 text-xs">
          {[['Konsumsi Terukur', '482 kWh/bln', '✓'], ['PLTS Optimal', '3.2 kWp', '✓'], ['Hemat/Tahun', 'Rp17.040.000', '✓'], ['PBP', '3.2 tahun', '✓'], ['Status Bank', 'LAYAK', '★']].map(([k, v, ic]) => (
            <div key={String(k)} className="flex justify-between items-center">
              <span style={{ color: 'var(--metal-mid)' }}>{k}</span>
              <span className="font-mono font-bold flex items-center gap-1" style={{ color: ic === '★' ? 'var(--eco-primary)' : 'var(--metal-dark)' }}>
                {ic} {v}
              </span>
            </div>
          ))}
        </div>
      </div>
    ),
  },
];

function FlipCard({ card, autoFlip }: { card: typeof CARDS[0]; autoFlip?: boolean }) {
  const [flipped, setFlipped] = useState(false);
  const done = useRef(false);

  useEffect(() => {
    if (!autoFlip || done.current) return;
    const t = setTimeout(() => { setFlipped(true); done.current = true; }, 1200);
    return () => clearTimeout(t);
  }, [autoFlip]);

  return (
    <div
      className="relative cursor-pointer"
      style={{ perspective: '800px', width: '100%', maxWidth: '220px', height: '280px' }}
      onClick={() => setFlipped((f) => !f)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && setFlipped((f) => !f)}
      aria-label={`Kartu ${card.id}: ${card.label}`}
    >
      <div
        style={{
          position: 'absolute', inset: 0,
          transformStyle: 'preserve-3d',
          transition: 'transform 0.5s cubic-bezier(0.4,0.2,0.2,1)',
          transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)',
        }}
      >
        {/* Front */}
        <div
          className="absolute inset-0 rounded-2xl p-5 flex flex-col items-center justify-between"
          style={{
            backfaceVisibility: 'hidden',
            WebkitBackfaceVisibility: 'hidden',
            background: 'var(--bg-paper)',
            border: '1.5px solid var(--border-soft)',
            boxShadow: 'var(--shadow-clay)',
          }}
        >
          <div className="flex flex-col items-center gap-3 mt-2">
            <span className="text-3xl">{card.icon}</span>
            <div className="text-center">
              <span className="text-xs font-bold" style={{ color: 'var(--metal-light)' }}>#{card.id}</span>
              <p className="font-bold mt-0.5" style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)' }}>{card.label}</p>
              <p className="text-xs mt-2 leading-relaxed" style={{ color: 'var(--metal-mid)' }}>{card.front}</p>
            </div>
          </div>
          <span className="text-xs" style={{ color: 'var(--metal-light)' }}>Klik untuk lihat demo →</span>
        </div>

        {/* Back */}
        <div
          className="absolute inset-0 rounded-2xl p-5 flex flex-col items-start justify-start overflow-hidden"
          style={{
            backfaceVisibility: 'hidden',
            WebkitBackfaceVisibility: 'hidden',
            transform: 'rotateY(180deg)',
            background: 'var(--metal-dark)',
            border: '1.5px solid #374151',
          }}
        >
          <span className="text-xs font-bold mb-3" style={{ color: 'var(--metal-light)' }}>#{card.id} DEMO</span>
          <div className="w-full" style={{ color: 'var(--metal-light)' }}>{card.back}</div>
        </div>
      </div>
    </div>
  );
}

export default function FeatureCards() {
  return (
    <section className="py-20 md:py-28 overflow-hidden" style={{ background: 'var(--bg-surface)' }}>
      <div className="max-w-5xl mx-auto px-4">
        <div className="text-center mb-14">
          <span className="inline-block text-xs font-bold tracking-widest uppercase mb-3" style={{ color: 'var(--eco-primary)' }}>
            FITUR
          </span>
          <h2 className="text-3xl md:text-4xl font-bold mb-3" style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)' }}>
            Dari deteksi sampai PLTS,<br className="hidden md:block" /> semua di satu nota
          </h2>
          <p className="text-sm md:text-base" style={{ color: 'var(--metal-mid)' }}>
            Empat langkah cerdas efisiensi energi. Balik kartunya untuk mencoba demonya.
          </p>
        </div>

        {/* Clothesline SVG */}
        <div className="relative">
          <svg
            className="w-full"
            viewBox="0 0 900 60"
            fill="none"
            preserveAspectRatio="none"
            style={{ height: '60px', marginBottom: '-24px' }}
          >
            <path
              d="M 20 20 Q 230 50 450 22 Q 670 -4 880 20"
              stroke="var(--metal-mid)"
              strokeWidth="2.5"
              strokeLinecap="round"
              fill="none"
            />
            {[135, 310, 500, 680].map((x, i) => (
              <g key={i}>
                {/* Clothespin */}
                <rect x={x - 5} y={15} width={10} height={18} rx={2} fill="var(--metal-light)" />
                <rect x={x - 2} y={33} width={4} height={6} rx={1} fill="#6B7280" />
              </g>
            ))}
          </svg>

          {/* Cards */}
          <div className="flex flex-wrap justify-center gap-6 md:gap-8 pt-6">
            {CARDS.map((card, i) => (
              <div
                key={card.id}
                style={{ animation: `pendulum 3s ease-in-out ${i * 0.4}s infinite alternate` }}
                className="flex flex-col items-center"
              >
                <FlipCard card={card} autoFlip={i === 0} />
              </div>
            ))}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes pendulum {
          from { transform: rotate(-1.5deg); }
          to   { transform: rotate(1.5deg); }
        }
      `}</style>
    </section>
  );
}
