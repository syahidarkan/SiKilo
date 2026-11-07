'use client';

import { useState, useEffect, useRef } from 'react';

const CARDS = [
  {
    id: '01',
    label: 'Tahu',
    tagline: 'Deteksi mesin boros',
    color: '#EF4444',
    colorBg: '#FEF2F2',
    front: 'Kenali setiap mesin yang boros daya, tanpa buka kabel.',
    back: (
      <div className="text-left w-full">
        <p className="text-xs font-bold mb-3" style={{ color: 'rgba(255,255,255,0.6)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>NILM Signal Fingerprint</p>
        <div className="space-y-2">
          {[['Kompresor Freezer', 85, '#EF4444'], ['Setrika Uap', 62, '#F97316'], ['Mesin Cuci', 48, '#3B82F6'], ['Lampu LED', 12, '#4ADE80']].map(([label, pct, color]) => (
            <div key={String(label)}>
              <div className="flex justify-between text-xs mb-1">
                <span style={{ color: 'rgba(255,255,255,0.75)' }}>{label}</span>
                <span className="font-mono font-bold" style={{ color: color as string }}>{pct}W</span>
              </div>
              <div className="h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.12)' }}>
                <div className="h-1.5 rounded-full transition-all" style={{ width: `${pct}%`, background: color as string }} />
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
    tagline: 'Jadwal cerdas AI',
    color: '#F97316',
    colorBg: '#FFF7ED',
    front: 'Jadwalkan mesin berat saat matahari sedang paling terik.',
    back: (
      <div className="text-left w-full">
        <p className="text-xs font-bold mb-3" style={{ color: 'rgba(255,255,255,0.6)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Jadwal AI Hari Ini</p>
        <div className="space-y-2">
          {[['08.00–10.00', 'Setrika Uap ON', '#FDE68A'], ['10.00–14.00', 'Mesin Cuci + Dryer', '#4ADE80'], ['14.00–16.00', 'Kompresor Maks', '#93C5FD'], ['17.00+', 'Mode Hemat', 'rgba(255,255,255,0.4)']].map(([time, act, color]) => (
            <div key={String(time)} className="flex gap-2 items-center">
              <span className="text-xs font-mono font-bold w-20 shrink-0" style={{ color: color as string }}>{time}</span>
              <span className="text-xs" style={{ color: 'rgba(255,255,255,0.75)' }}>{act}</span>
            </div>
          ))}
        </div>
      </div>
    ),
  },
  {
    id: '03',
    label: 'Hemat',
    tagline: 'Notifikasi WhatsApp',
    color: '#2FBF71',
    colorBg: '#D2F5E1',
    front: 'Rekomendasi harian langsung di WhatsApp grup kamu.',
    back: (
      <div className="text-left w-full space-y-2">
        <div className="rounded-xl px-3 py-2.5 text-xs" style={{ background: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.1)' }}>
          <span className="font-bold block mb-1" style={{ color: '#4ADE80' }}>⚡ Si Kilo</span>
          <span style={{ color: 'rgba(255,255,255,0.8)' }}>Matahari terik 10–14. Setrika & cuci: ON sekarang 🌞</span>
        </div>
        <div className="rounded-xl px-3 py-2.5 text-xs" style={{ background: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.1)' }}>
          <span className="font-bold block mb-1" style={{ color: '#4ADE80' }}>⚡ Si Kilo</span>
          <span style={{ color: 'rgba(255,255,255,0.8)' }}>Tagihan pekan ini turun 28%! Hemat Rp340rb 🎉</span>
        </div>
      </div>
    ),
  },
  {
    id: '04',
    label: 'Punya PLTS',
    tagline: 'Rapor kelayakan bank',
    color: '#FF9E2C',
    colorBg: '#FFF3E0',
    front: 'Dapatkan laporan kelayakan bank dari data energi nyata.',
    back: (
      <div className="text-left w-full">
        <p className="text-xs font-bold mb-3" style={{ color: 'rgba(255,255,255,0.6)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Energy Credit Scorecard</p>
        <div className="space-y-2 text-xs">
          {[['Konsumsi Terukur', '482 kWh/bln', true], ['PLTS Optimal', '3.2 kWp', true], ['Hemat/Tahun', 'Rp17.040.000', true], ['PBP', '3.2 tahun', true], ['Status Bank', 'LAYAK ★', true]].map(([k, v, ok]) => (
            <div key={String(k)} className="flex justify-between items-center py-0.5" style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
              <span style={{ color: 'rgba(255,255,255,0.65)' }}>{k}</span>
              <span className="font-mono font-bold" style={{ color: ok ? '#4ADE80' : 'rgba(255,255,255,0.4)' }}>{v}</span>
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
    const t = setTimeout(() => { setFlipped(true); done.current = true; }, 1600);
    return () => clearTimeout(t);
  }, [autoFlip]);

  return (
    <div
      className="relative cursor-pointer select-none"
      style={{ perspective: '900px', width: '100%', maxWidth: '220px', height: '290px' }}
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
          transition: 'transform 0.55s cubic-bezier(0.4,0.2,0.2,1)',
          transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)',
        }}
      >
        {/* Front */}
        <div
          className="absolute inset-0 rounded-2xl p-5 flex flex-col justify-between"
          style={{
            backfaceVisibility: 'hidden',
            WebkitBackfaceVisibility: 'hidden',
            background: '#FFFFFF',
            border: '1.5px solid var(--border-soft)',
            boxShadow: '0 8px 24px -8px rgba(31,41,55,0.10)',
          }}
        >
          <div>
            {/* Number + icon badge */}
            <div className="flex items-center justify-between mb-4">
              <span
                className="text-xs font-black"
                style={{ color: 'var(--metal-light)', letterSpacing: '0.06em' }}
              >
                #{card.id}
              </span>
              <div
                className="w-9 h-9 rounded-xl flex items-center justify-center text-base font-bold"
                style={{ background: card.colorBg, color: card.color }}
              >
                {card.id === '01' ? '🔌' : card.id === '02' ? '⏰' : card.id === '03' ? '📱' : '📋'}
              </div>
            </div>
            {/* Title */}
            <p
              className="font-extrabold text-lg mb-1 leading-tight"
              style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}
            >
              {card.label}
            </p>
            <p className="text-xs font-semibold mb-3" style={{ color: card.color }}>
              {card.tagline}
            </p>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--metal-mid)' }}>
              {card.front}
            </p>
          </div>
          {/* Hint */}
          <div className="flex items-center gap-1 mt-2">
            <span className="text-xs" style={{ color: 'var(--metal-light)' }}>Balik kartu</span>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M2 6h8M7 3l3 3-3 3" stroke="var(--metal-light)" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </div>

        {/* Back */}
        <div
          className="absolute inset-0 rounded-2xl p-5 flex flex-col"
          style={{
            backfaceVisibility: 'hidden',
            WebkitBackfaceVisibility: 'hidden',
            transform: 'rotateY(180deg)',
            background: `linear-gradient(145deg, ${card.color}EE 0%, ${card.color}BB 100%)`,
            border: `1.5px solid ${card.color}`,
          }}
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-black" style={{ color: 'rgba(255,255,255,0.6)', letterSpacing: '0.06em' }}>
              #{card.id} DEMO
            </span>
            <div className="w-5 h-5 rounded-full flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.2)' }}>
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M2 5h6M5 2l3 3-3 3" stroke="white" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>
          <div className="flex-1 overflow-hidden">{card.back}</div>
        </div>
      </div>
    </div>
  );
}

export default function FeatureCards() {
  return (
    <section className="py-24 md:py-32 overflow-hidden" style={{ background: 'var(--bg-surface)' }}>
      <div className="max-w-5xl mx-auto px-4">

        {/* Section header */}
        <div className="text-center mb-14">
          <span
            className="inline-flex items-center gap-1.5 text-xs font-bold tracking-widest uppercase mb-4 px-3 py-1 rounded-full"
            style={{ background: 'var(--eco-light)', color: 'var(--eco-dark)' }}
          >
            ⚡ Fitur
          </span>
          <h2
            className="text-3xl md:text-4xl font-extrabold mb-3 leading-tight"
            style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)', letterSpacing: '-0.03em' }}
          >
            Dari deteksi sampai PLTS,<br className="hidden md:block" /> semua di satu nota
          </h2>
          <p className="text-sm md:text-base" style={{ color: 'var(--metal-mid)' }}>
            Empat langkah cerdas efisiensi energi. Balik kartunya untuk mencoba demonya.
          </p>
        </div>

        {/* Clothesline */}
        <div className="relative">
          <svg
            className="w-full"
            viewBox="0 0 900 60"
            fill="none"
            preserveAspectRatio="none"
            style={{ height: '60px', marginBottom: '-20px' }}
          >
            <path
              d="M 20 20 Q 230 50 450 22 Q 670 -4 880 20"
              stroke="var(--border-medium)"
              strokeWidth="2"
              strokeLinecap="round"
              fill="none"
            />
            {[135, 310, 500, 680].map((x, i) => (
              <g key={i}>
                <rect x={x - 4} y={14} width={8} height={16} rx={2} fill="var(--metal-light)" />
                <rect x={x - 1.5} y={30} width={3} height={5} rx={1} fill="var(--border-medium)" />
              </g>
            ))}
          </svg>

          {/* Cards */}
          <div className="flex flex-wrap justify-center gap-5 md:gap-7 pt-4">
            {CARDS.map((card, i) => (
              <div
                key={card.id}
                className="flex flex-col items-center"
                style={{ animation: `swing 3.5s ease-in-out ${i * 0.35}s infinite alternate` }}
              >
                <FlipCard card={card} autoFlip={i === 0} />
              </div>
            ))}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes swing {
          from { transform: rotate(-1deg); }
          to   { transform: rotate(1deg); }
        }
      `}</style>
    </section>
  );
}
