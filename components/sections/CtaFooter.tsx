'use client';

import { useRef, useState } from 'react';
import { ArrowRight, ArrowUp, Mail, Zap } from 'lucide-react';
import Reveal from '@/components/Reveal';
import KiloAvatar from '@/components/KiloAvatar';
import { useGaze, useOnceInView, useReducedMotion } from '@/components/hooks';

const PRODUCT_LINKS = [
  { label: 'Nota Listrik Cerdas', href: '#fitur' },
  { label: 'AI Dispatcher', href: '#fitur' },
  { label: 'Solar Right-Sizing', href: '#simulator-section' },
  { label: 'Energy Credit Scorecard', href: '#fitur' },
];

export default function CtaFooter() {
  const reduced = useReducedMotion();
  const ctaRef = useRef<HTMLElement>(null);
  const [risen, setRisen] = useState(false);

  useGaze(ctaRef, reduced);
  useOnceInView(ctaRef, () => setRisen(true), 0.3);

  // The glow drifts a little with the pointer.
  const onMove = (e: React.PointerEvent<HTMLElement>) => {
    if (reduced || e.pointerType === 'touch') return;
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty('--px', (((e.clientX - r.left) / r.width) * 2 - 1).toFixed(3));
  };

  return (
    <>
      <section
        ref={ctaRef}
        onPointerMove={onMove}
        className={`cta py-24 md:py-32 relative overflow-hidden ${risen ? 'cta-in' : ''}`}
        style={{ background: '#0F2820' }}
        aria-labelledby="h-cta"
      >
        <div className="cta-glow" aria-hidden="true" />
        <div className="cta-grid" aria-hidden="true" />

        <div className="relative max-w-3xl mx-auto px-4 text-center">
          <Reveal>
            <div className="cta-kilo mx-auto mb-6">
              <KiloAvatar className="cta-kilo-av" />
            </div>

            <h2
              id="h-cta"
              className="text-3xl md:text-5xl font-extrabold mb-5 leading-tight"
              style={{ color: '#fff', fontFamily: 'var(--font-display)', letterSpacing: '-0.03em' }}
            >
              Tagihan lebih kecil.<br />
              <span style={{ color: '#4ADE80' }}>Mimpi PLTS makin dekat.</span>
            </h2>
            <p className="text-sm md:text-base mb-10 max-w-lg mx-auto leading-relaxed" style={{ color: '#86EFAC' }}>
              Mulai gratis dengan Nota Listrik Cerdas. Upgrade ke AI Dispatcher kapan saja kamu siap.
            </p>

            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <a href="#simulator-section" className="cta-btn cta-btn-main">
                <Zap size={16} fill="currentColor" />
                Coba Simulator Gratis
                <ArrowRight size={16} className="cta-arrow" />
              </a>
              <a
                href="mailto:syhd.acan@gmail.com?subject=WASKITA - Daftar Early Access"
                className="cta-btn cta-btn-ghost"
              >
                <Mail size={16} />
                Daftar Early Access
              </a>
            </div>

            <p className="mt-7 text-xs" style={{ color: 'rgba(134,239,172,0.7)' }}>
              Tidak perlu kartu kredit · Tidak perlu pasang hardware · Mulai dalam 5 menit
            </p>
          </Reveal>
        </div>
      </section>

      <footer style={{ background: '#0A1E14' }}>
        <div className="max-w-5xl mx-auto px-4 py-10">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-10">
            <div>
              <div className="flex items-center gap-2 mb-3">
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center"
                  style={{ background: 'var(--eco-primary)', color: '#fff' }}
                >
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
                    style={{ background: '#0F2820', color: '#6FA687', border: '1px solid #1D3A2E' }}
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
      </footer>
    </>
  );
}
