'use client';

import { useState, type ReactNode } from 'react';
import { Plug, Clock, Smartphone, ClipboardList, Zap, RotateCw } from 'lucide-react';
import SectionHead from '@/components/SectionHead';
import KiloAvatar from '@/components/KiloAvatar';

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
    tagline: 'Kenali mesin yang boros',
    color: '#DC2626',
    colorBg: '#FEF2F2',
    icon: <Plug size={26} />,
    front: 'Satu sensor di panel sudah cukup untuk melihat mesin mana yang paling banyak menyedot listrik.',
    back: (on) => (
      <div className="text-left w-full">
        {backTitle('Contoh: jejak beban tiap mesin')}
        <div className="space-y-2.5">
          {([['Kompresor freezer', 85, '#FECACA'], ['Setrika uap', 62, '#FED7AA'], ['Mesin cuci', 48, '#BFDBFE'], ['Lampu LED', 12, '#BBF7D0']] as const).map(
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
    tagline: 'Jadwal yang lebih cerdas',
    color: '#C2410C',
    colorBg: '#FFF7ED',
    icon: <Clock size={26} />,
    front: 'Mesin yang bisa ditunda dijadwalkan ulang ke jam terik, supaya listrik surya langsung terpakai.',
    back: (on) => (
      <div className="text-left w-full">
        {backTitle('Contoh: jadwal hari ini')}
        <div className="space-y-2">
          {([['08.00–10.00', 'Setrika uap menyala', '#FDE68A'], ['10.00–14.00', 'Mesin cuci dan pengering', '#BBF7D0'], ['14.00–16.00', 'Kompresor beban penuh', '#BFDBFE'], ['Setelah 17.00', 'Mode hemat', 'rgba(255,255,255,0.65)']] as const).map(
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
    tagline: 'Laporan lewat WhatsApp',
    color: '#15803D',
    colorBg: '#D2F5E1',
    icon: <Smartphone size={26} />,
    front: 'Rekomendasi harian dan ringkasan penghematan dikirim ke WhatsApp, tanpa perlu membuka aplikasi lain.',
    back: (on) => (
      <div className="text-left w-full space-y-2">
        <div style={{ opacity: on ? 1 : 0, transform: on ? 'none' : 'translateY(8px)', transition: 'all 0.45s ease 0.35s' }}>
          <KiloBubble>Matahari terik pukul 10.00 sampai 14.00. Cuci dan setrika bisa dinyalakan sekarang.</KiloBubble>
        </div>
        <div style={{ opacity: on ? 1 : 0, transform: on ? 'none' : 'translateY(8px)', transition: 'all 0.45s ease 0.85s' }}>
          <KiloBubble>Tagihan pekan ini lebih rendah daripada pekan lalu.</KiloBubble>
        </div>
      </div>
    ),
  },
  {
    id: '04',
    label: 'Punya PLTS',
    tagline: 'Rapor untuk bank',
    color: '#B45309',
    colorBg: '#FFF3E0',
    icon: <ClipboardList size={26} />,
    front: 'Data pemakaian yang terukur disusun menjadi rapor kelayakan PLTS yang bisa Anda lampirkan saat mengajukan pembiayaan.',
    back: (on) => (
      <div className="text-left w-full">
        {backTitle('Contoh: rapor kelayakan')}
        <div className="space-y-1.5 text-xs">
          {([['Konsumsi terukur', '482 kWh per bulan'], ['PLTS optimal', '3,2 kWp'], ['Hemat per tahun', 'Rp17.040.000'], ['Balik modal', '3,2 tahun'], ['Status kelayakan', 'Layak']] as const).map(
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
      style={{ perspective: '900px', width: '100%', height: 380 }}
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
          className="fc-face rounded-3xl p-5 flex flex-col justify-between"
          style={{ background: 'var(--panel)', border: '1.5px solid var(--border-soft)', boxShadow: '0 8px 24px -8px rgba(31,41,55,0.10)' }}
        >
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold" style={{ color: 'var(--metal-mid)', letterSpacing: '0.14em', fontFamily: 'var(--font-mono)' }}>FITUR</span>
              <span className="text-xs font-bold" style={{ color: 'var(--metal-mid)', letterSpacing: '0.1em', fontFamily: 'var(--font-mono)' }}>#{card.id}</span>
            </div>
            <div
              className="rounded-2xl flex items-center justify-center mb-4"
              style={{ background: `color-mix(in srgb, ${card.color} 14%, var(--panel))`, height: 96, color: `color-mix(in srgb, ${card.color} 75%, var(--metal-dark))` }}
              aria-hidden="true"
            >
              <span className="w-14 h-14 rounded-full flex items-center justify-center" style={{ background: 'var(--panel)', boxShadow: '0 8px 18px -8px rgba(31,41,55,0.25)' }}>
                {card.icon}
              </span>
            </div>
            <p
              className="font-extrabold text-xl mb-1 leading-tight"
              style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}
            >
              {card.label}
            </p>
            <p className="text-xs font-semibold mb-2" style={{ color: `color-mix(in srgb, ${card.color} 75%, var(--metal-dark))` }}>{card.tagline}</p>
            <p className="text-sm leading-relaxed" style={{ color: 'var(--metal-mid)' }}>{card.front}</p>
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
  return (
    <section id="fitur" className="sheet-band">
      <div className="sheet-w">
        <SectionHead
          n="03"
          label="Fitur"
          title="Dari pembacaan beban sampai rapor untuk bank"
          lead="Empat tahap yang saling menyambung. Balik setiap kartu untuk melihat contoh tampilannya."
        />

        <div className="fc-grid">
          {CARDS.map((card) => (
            <FlipCard key={card.id} card={card} />
          ))}
        </div>
      </div>
    </section>
  );
}
