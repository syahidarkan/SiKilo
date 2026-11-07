'use client';

import { useMemo, useRef, useState } from 'react';
import { ArrowRight, ArrowUp, UserPlus, Zap } from 'lucide-react';
import { REGISTER_URL } from '@/lib/waskita';
import Reveal from '@/components/Reveal';
import KiloAvatar from '@/components/KiloAvatar';
import { useGaze, useOnceInView, useReducedMotion } from '@/components/hooks';

const PRODUCT_LINKS = [
  { label: 'Nota Listrik Cerdas', href: '#fitur' },
  { label: 'AI Dispatcher', href: '#fitur' },
  { label: 'Solar Right-Sizing', href: '#simulator-section' },
  { label: 'Energy Credit Scorecard', href: '#fitur' },
];

/** Deretan gedung deterministik (tanpa random saat render, supaya server dan klien sama). */
function skyline(seed: number, body: string, win: string, hMin: number, hMax: number, panels = false) {
  let s = seed;
  const rnd = () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
  const out: React.ReactNode[] = [];
  let x = -10;
  let k = 0;
  while (x < 1210) {
    const w = 48 + Math.floor(rnd() * 46);
    const h = hMin + Math.floor(rnd() * (hMax - hMin));
    const y = 200 - h;
    out.push(<rect key={`b${k}`} x={x} y={y} width={w} height={h + 4} rx={3} fill={body} />);
    if (panels && rnd() < 0.55) {
      out.push(<rect key={`p${k}`} x={x + 6} y={y - 5} width={Math.min(w - 12, 30)} height={5} rx={1.5} fill="#2a5d8f" />);
    }
    for (let wy = y + 12; wy < 188; wy += 22) {
      for (let wx = x + 10; wx < x + w - 10; wx += 18) {
        if (rnd() < 0.62) out.push(<rect key={`w${k}-${wx}-${wy}`} x={wx} y={wy} width={7} height={9} rx={1.5} fill={win} />);
      }
    }
    x += w + 3;
    k++;
  }
  return out;
}

export default function CtaFooter() {
  const reduced = useReducedMotion();
  const ctaRef = useRef<HTMLElement>(null);
  const [risen, setRisen] = useState(false);

  useGaze(ctaRef, reduced);
  useOnceInView(ctaRef, () => setRisen(true), 0.3);

  const far = useMemo(() => skyline(11, '#f3d9a8', '#fff3d3', 60, 150), []);
  const near = useMemo(() => skyline(23, '#bcdcc0', '#e9f7dd', 50, 100, true), []);

  // Matahari dan langit bergeser sedikit mengikuti pointer.
  const onMove = (e: React.PointerEvent<HTMLElement>) => {
    if (reduced || e.pointerType === 'touch') return;
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty('--px', (((e.clientX - r.left) / r.width) * 2 - 1).toFixed(3));
  };

  return (
    <>
      <section ref={ctaRef} onPointerMove={onMove} className={`bal ${risen ? 'in' : ''}`} aria-labelledby="h-cta">
        <div className="bal-sun" aria-hidden="true"><i /></div>
        <svg className="bal-clouds" viewBox="0 0 1200 200" preserveAspectRatio="xMidYMin slice" aria-hidden="true">
          <g className="c1">
            <ellipse cx="220" cy="70" rx="70" ry="20" fill="#fff" opacity=".7" />
            <ellipse cx="270" cy="58" rx="46" ry="18" fill="#fff" opacity=".7" />
            <ellipse cx="180" cy="62" rx="40" ry="14" fill="#fff" opacity=".7" />
          </g>
          <g className="c2">
            <ellipse cx="900" cy="110" rx="80" ry="20" fill="#fff" opacity=".6" />
            <ellipse cx="950" cy="98" rx="50" ry="17" fill="#fff" opacity=".6" />
          </g>
        </svg>
        <svg className="bal-sky far" viewBox="0 0 1200 200" preserveAspectRatio="xMidYMax slice" aria-hidden="true">{far}</svg>
        <svg className="bal-sky near" viewBox="0 0 1200 200" preserveAspectRatio="xMidYMax slice" aria-hidden="true">{near}</svg>

        <div className="bal-copy">
          <Reveal>
            <div className="sh-mark" style={{ justifyContent: 'center' }}>
              <b>05</b>
              <span>Mulai</span>
            </div>
            <h2 id="h-cta">
              Tagihan lebih kecil. <em>Mimpi PLTS makin dekat.</em>
            </h2>
            <p>Mulai gratis dengan Nota Listrik Cerdas. Upgrade ke AI Dispatcher kapan saja kamu siap.</p>
            <div className="bal-cta">
              <a href="#simulator-section" className="bal-btn main">
                <Zap size={16} fill="currentColor" />
                Coba Simulator Gratis
                <ArrowRight size={16} />
              </a>
              <a href={REGISTER_URL} className="bal-btn line">
                <UserPlus size={16} />
                Daftar &amp; Buka Dasbor
              </a>
            </div>
            <p className="bal-note">Tidak perlu kartu kredit · Tidak perlu pasang hardware · Mulai dalam 5 menit</p>
          </Reveal>
        </div>

        <svg className="bal-floor" viewBox="0 0 1200 280" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
          <rect x="0" y="176" width="1200" height="12" rx="6" fill="#b8ad96" />
          <rect x="0" y="188" width="1200" height="92" fill="#ecd9aa" />
          <rect x="0" y="188" width="1200" height="5" fill="#d9bf86" />
          <rect x="0" y="262" width="1200" height="18" fill="#d1b277" />
          <ellipse cx="600" cy="236" rx="110" ry="9" fill="#22301f" opacity=".14" />
          {[150, 330, 870, 1050].map((cx, i) => (
            <g key={cx} className="bal-panel" style={{ ['--g' as string]: `${1 + i * 0.35}s` }}>
              <path d={`M${cx - 20} 186 L${cx - 16} 150 M${cx + 44} 186 L${cx + 40} 150`} stroke="#6b7280" strokeWidth="5" strokeLinecap="round" />
              <path d={`M${cx - 62} 152 L${cx + 62} 152 L${cx + 84} 78 L${cx - 40} 78 Z`} fill="#2a5d8f" stroke="#e5e7eb" strokeWidth="4" strokeLinejoin="round" />
              <path d={`M${cx - 21} 152 L${cx + 1} 78 M${cx + 21} 152 L${cx + 43} 78 M${cx - 51} 115 L${cx + 73} 115`} stroke="#8fb3d6" strokeWidth="2" opacity=".7" />
              <path d={`M${cx - 52} 140 L${cx - 20} 90`} stroke="#fff" strokeWidth="5" strokeLinecap="round" opacity=".18" />
            </g>
          ))}
          <path d="M150 188 C300 214 460 214 560 200 M1050 188 C900 214 760 214 660 200" stroke="#1f2937" strokeWidth="3" fill="none" strokeLinecap="round" opacity=".55" />
        </svg>
        <div className="bal-kilo" aria-hidden="true">
          <KiloAvatar />
        </div>
      </section>

      <footer className="site-footer">
        <div className="sf-wave" aria-hidden="true">
          <svg viewBox="0 0 1440 250" preserveAspectRatio="none">
            <path className="sf-1" d="M0,90 C120,100 180,118 260,116 C420,112 560,95 720,100 C880,105 1000,50 1150,50 C1280,50 1380,70 1440,80 L1440,250 L0,250 Z" />
            <path className="sf-2" d="M0,125 C200,125 420,170 720,172 C980,174 1200,140 1440,135 L1440,250 L0,250 Z" />
            <path className="sf-3" d="M0,150 C260,150 480,200 740,198 C1000,196 1240,165 1440,160 L1440,250 L0,250 Z" />
          </svg>
        </div>
        <div className="sf-body">
          <div className="max-w-5xl mx-auto px-4 py-8">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-10">
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'var(--eco-primary)', color: '#fff' }}>
                    <Zap size={14} fill="currentColor" />
                  </div>
                  <span className="font-black text-sm tracking-tight" style={{ color: '#fff' }}>
                    WAS<span style={{ color: 'var(--eco-primary)' }}>KITA</span>
                  </span>
                </div>
                <p className="text-xs leading-relaxed" style={{ color: '#6FA687' }}>
                  AI Energy Dispatcher &amp; Solar Right-Sizing untuk UMKM Indonesia.
                </p>
              </div>

              <div>
                <p className="text-xs font-bold tracking-widest uppercase mb-3" style={{ color: '#4C9A74' }}>Produk</p>
                <ul className="space-y-1.5 text-xs" style={{ color: '#6FA687' }}>
                  {PRODUCT_LINKS.map(({ label, href }) => (
                    <li key={label}>
                      <a href={href} className="transition-colors hover:text-green-400 focus-visible:text-green-400">
                        {label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <p className="text-xs font-bold tracking-widest uppercase mb-3" style={{ color: '#4C9A74' }}>Didukung Oleh</p>
                <div className="flex flex-wrap gap-1.5">
                  {['PLN Icon', 'BRI UMKM', 'Kementerian ESDM', 'UNS Innovation'].map((name) => (
                    <div
                      key={name}
                      className="px-2.5 py-1 rounded-lg text-xs font-semibold"
                      style={{ background: '#13352a', color: '#6FA687', border: '1px solid #1D3A2E' }}
                    >
                      {name}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div
              className="pt-6 flex flex-col md:flex-row items-center justify-between gap-3 text-xs"
              style={{ borderTop: '1px solid #1D3A2E', color: '#6FA687' }}
            >
              <span>© 2026 WASKITA · UNS Innovation Hackathon · Energy Track Sub-tema C</span>
              <a href="#top" className="cta-top">
                Kembali ke atas <ArrowUp size={13} />
              </a>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
}
