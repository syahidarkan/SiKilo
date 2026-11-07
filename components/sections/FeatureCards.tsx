'use client';

import { useRef, useState, type ReactNode } from 'react';
import { Plug, Clock, Smartphone, ClipboardList, Zap, RotateCw } from 'lucide-react';
import Reveal from '@/components/Reveal';
import KiloAvatar from '@/components/KiloAvatar';
import { useOnceInView } from '@/components/hooks';

type Card = {
  id: string;
  label: string;
  tagline: string;
  color: string;
  colorBg: string;
  icon: ReactNode;
  front: string;
  back: (on: boolean) => ReactNode;
};

const backTitle = (t: string) => (
  <p className="text-xs font-bold mb-3" style={{ color: 'rgba(255,255,255,0.75)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
    {t}
  </p>
);

const KiloBubble = ({ children }: { children: ReactNode }) => (
  <div
    className="rounded-xl px-3 py-2.5 text-xs flex gap-2 items-start"
    style={{ background: 'rgba(255,255,255,0.14)', border: '1px solid rgba(255,255,255,0.12)' }}
  >
    <KiloAvatar className="shrink-0" />
    <span style={{ color: 'rgba(255,255,255,0.92)' }}>
      <span className="font-bold block mb-0.5">Si Kilo</span>
      {children}
    </span>
  </div>
);

const CARDS: Card[] = [
  {
    id: '01',
    label: 'Tahu',
    tagline: 'Deteksi mesin boros',
    color: '#DC2626',
    colorBg: '#FEF2F2',
    icon: <Plug size={18} />,
    front: 'Kenali setiap mesin yang boros daya, tanpa buka kabel.',
    back: (on) => (
      <div className="text-left w-full">
        {backTitle('NILM Signal Fingerprint')}
        <div className="space-y-2.5">
          {([['Kompresor Freezer', 85, '#FECACA'], ['Setrika Uap', 62, '#FED7AA'], ['Mesin Cuci', 48, '#BFDBFE'], ['Lampu LED', 12, '#BBF7D0']] as const).map(
            ([label, pct, color], i) => (
              <div key={label}>
                <div className="flex justify-between text-xs mb-1">
                  <span style={{ color: 'rgba(255,255,255,0.9)' }}>{label}</span>
                  <span className="font-mono font-bold" style={{ color }}>{pct}W</span>
                </div>
                <div className="h-1.5 rounded-full" style={{ background: 'rgba(255,255,255,0.18)' }}>
                  <div
                    className="h-1.5 rounded-full"
                    style={{
                      width: on ? `${pct}%` : '0%',
                      background: color,
                      transition: `width 0.8s cubic-bezier(0.2,0.8,0.2,1) ${0.35 + i * 0.12}s`,
                    }}
                  />
                </div>
              </div>
            ),
          )}
        </div>
      </div>
    ),
  },
  {
    id: '02',
    label: 'Atur',
    tagline: 'Jadwal cerdas AI',
    color: '#C2410C',
    colorBg: '#FFF7ED',
    icon: <Clock size={18} />,
    front: 'Jadwalkan mesin berat saat matahari sedang paling terik.',
    back: (on) => (
      <div className="text-left w-full">
        {backTitle('Jadwal AI Hari Ini')}
        <div className="space-y-2">
          {([['08.00–10.00', 'Setrika Uap ON', '#FDE68A'], ['10.00–14.00', 'Mesin Cuci + Dryer', '#BBF7D0'], ['14.00–16.00', 'Kompresor Maks', '#BFDBFE'], ['17.00+', 'Mode Hemat', 'rgba(255,255,255,0.65)']] as const).map(
            ([time, act, color], i) => (
              <div
                key={time}
                className="flex gap-2 items-center"
                style={{
                  opacity: on ? 1 : 0,
                  transform: on ? 'none' : 'translateX(-8px)',
                  transition: `opacity 0.4s ease ${0.35 + i * 0.12}s, transform 0.4s ease ${0.35 + i * 0.12}s`,
                }}
              >
                <span className="text-xs font-mono font-bold w-20 shrink-0" style={{ color }}>{time}</span>
                <span className="text-xs" style={{ color: 'rgba(255,255,255,0.92)' }}>{act}</span>
              </div>
            ),
          )}
        </div>
      </div>
    ),
  },
  {
    id: '03',
    label: 'Hemat',
    tagline: 'Notifikasi WhatsApp',
    color: '#15803D',
    colorBg: '#D2F5E1',
    icon: <Smartphone size={18} />,
    front: 'Rekomendasi harian langsung di WhatsApp grup kamu.',
    back: (on) => (
      <div className="text-left w-full space-y-2">
        <div style={{ opacity: on ? 1 : 0, transform: on ? 'none' : 'translateY(8px)', transition: 'all 0.45s ease 0.35s' }}>
          <KiloBubble>Matahari terik 10–14. Setrika dan cuci: ON sekarang.</KiloBubble>
        </div>
        <div style={{ opacity: on ? 1 : 0, transform: on ? 'none' : 'translateY(8px)', transition: 'all 0.45s ease 0.85s' }}>
          <KiloBubble>Tagihan pekan ini turun 28%! Hemat Rp340rb.</KiloBubble>
        </div>
      </div>
    ),
  },
  {
    id: '04',
    label: 'Punya PLTS',
    tagline: 'Rapor kelayakan bank',
    color: '#B45309',
    colorBg: '#FFF3E0',
    icon: <ClipboardList size={18} />,
    front: 'Dapatkan laporan kelayakan bank dari data energi nyata.',
    back: (on) => (
      <div className="text-left w-full">
        {backTitle('Energy Credit Scorecard')}
        <div className="space-y-1.5 text-xs">
          {([['Konsumsi Terukur', '482 kWh/bln'], ['PLTS Optimal', '3.2 kWp'], ['Hemat/Tahun', 'Rp17.040.000'], ['PBP', '3.2 tahun'], ['Status Bank', 'LAYAK']] as const).map(
            ([k, v], i) => (
              <div
                key={k}
                className="flex justify-between items-center py-0.5"
                style={{
                  borderBottom: '1px solid rgba(255,255,255,0.18)',
                  opacity: on ? 1 : 0,
                  transition: `opacity 0.4s ease ${0.3 + i * 0.1}s`,
                }}
              >
                <span style={{ color: 'rgba(255,255,255,0.85)' }}>{k}</span>
                <span className="font-mono font-bold" style={{ color: '#fff' }}>{v}</span>
              </div>
            ),
          )}
        </div>
      </div>
    ),
  },
];

function FlipCard({ card }: { card: Card }) {
  const [flipped, setFlipped] = useState(false);
  const toggle = () => setFlipped((f) => !f);

  return (
    <div
      className="fc relative cursor-pointer select-none"
      style={{ perspective: '900px', width: '100%', maxWidth: 220, height: 290 }}
      onClick={toggle}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          toggle();
        }
      }}
      role="button"
      tabIndex={0}
      aria-pressed={flipped}
      aria-label={`Kartu ${card.id}: ${card.label}. ${card.tagline}. Tekan untuk ${flipped ? 'kembali' : 'melihat demo'}`}
    >
      <div
        className="fc-inner"
        style={{ transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)' }}
      >
        {/* Front */}
        <div
          className="fc-face rounded-2xl p-5 flex flex-col justify-between"
          style={{ background: '#FFFFFF', border: '1.5px solid var(--border-soft)', boxShadow: '0 8px 24px -8px rgba(31,41,55,0.10)' }}
        >
          <div>
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-black" style={{ color: 'var(--metal-mid)', letterSpacing: '0.06em' }}>#{card.id}</span>
              <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: card.colorBg, color: card.color }}>
                {card.icon}
              </div>
            </div>
            <p
              className="font-extrabold text-lg mb-1 leading-tight"
              style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}
            >
              {card.label}
            </p>
            <p className="text-xs font-semibold mb-3" style={{ color: card.color }}>{card.tagline}</p>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--metal-mid)' }}>{card.front}</p>
          </div>
          <div className="flex items-center gap-1.5 mt-2" style={{ color: 'var(--metal-mid)' }}>
            <RotateCw size={12} className="fc-hint" />
            <span className="text-xs font-semibold">Balik kartu</span>
          </div>
        </div>

        {/* Back */}
        <div
          className="fc-face fc-back rounded-2xl p-5 flex flex-col"
          style={{ background: `linear-gradient(145deg, ${card.color} 0%, ${card.color}E6 100%)`, border: `1.5px solid ${card.color}` }}
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-black" style={{ color: 'rgba(255,255,255,0.8)', letterSpacing: '0.06em' }}>#{card.id} DEMO</span>
            <Zap size={14} color="#fff" fill="#fff" />
          </div>
          <div className="flex-1 overflow-hidden">{card.back(flipped)}</div>
        </div>
      </div>
    </div>
  );
}

export default function FeatureCards() {
  const lineRef = useRef<HTMLDivElement>(null);
  const [hung, setHung] = useState(false);
  useOnceInView(lineRef, () => setHung(true), 0.25);

  return (
    <section id="fitur" className="py-24 md:py-32 overflow-hidden" style={{ background: 'var(--bg-surface)' }}>
      <div className="max-w-5xl mx-auto px-4">
        <Reveal>
          <div className="text-center mb-14">
            <span
              className="inline-flex items-center gap-1.5 text-xs font-bold tracking-widest uppercase mb-4 px-3 py-1 rounded-full"
              style={{ background: 'var(--eco-light)', color: 'var(--eco-dark)' }}
            >
              <Zap size={13} strokeWidth={2.6} /> Fitur
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
        </Reveal>

        <div ref={lineRef} className={`relative fc-line ${hung ? 'hung' : ''}`}>
          <svg className="w-full hidden md:block" viewBox="0 0 900 60" fill="none" preserveAspectRatio="none" style={{ height: 60, marginBottom: -20 }} aria-hidden="true">
            <path
              className="fc-rope"
              d="M 20 20 Q 230 50 450 22 Q 670 -4 880 20"
              stroke="var(--border-medium)"
              strokeWidth="2"
              strokeLinecap="round"
              fill="none"
              pathLength={1}
            />
            {[135, 310, 500, 680].map((x) => (
              <g key={x}>
                <rect x={x - 4} y={14} width={8} height={16} rx={2} fill="var(--metal-light)" />
                <rect x={x - 1.5} y={30} width={3} height={5} rx={1} fill="var(--border-medium)" />
              </g>
            ))}
          </svg>

          <div className="flex flex-wrap justify-center gap-5 md:gap-7 pt-4">
            {CARDS.map((card, i) => (
              <div
                key={card.id}
                className="fc-drop flex flex-col items-center"
                style={{ ['--i' as string]: i }}
              >
                <div className="fc-swing">
                  <FlipCard card={card} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
