'use client';

import { ArrowRight, ArrowUp, UserPlus, Zap } from 'lucide-react';
import { REGISTER_URL } from '@/lib/waskita';
import Reveal from '@/components/Reveal';

const PRODUCT_LINKS = [
  { label: 'Nota Listrik Cerdas', href: '#fitur' },
  { label: 'AI Dispatcher', href: '#fitur' },
  { label: 'Solar Right-Sizing', href: '#simulator-section' },
  { label: 'Energy Credit Scorecard', href: '#fitur' },
];

export default function CtaFooter() {
  return (
    <>
      <section className="close" aria-labelledby="h-cta">
        <div className="sheet-w">
          <Reveal>
            <div className="sh-mark" style={{ justifyContent: 'center' }}>
              <b>05</b>
              <span>Mulai</span>
            </div>
            <h2 id="h-cta" className="close-title">
              Hitung dulu, pasang kemudian.
            </h2>
            <p className="close-lead">
              Masukkan daya PLN dan mesin di usahamu. Perkiraan ukuran PLTS dan waktu balik modal langsung muncul di simulator.
            </p>
            <div className="bal-cta">
              <a href="#simulator-section" className="bal-btn main">
                <Zap size={16} fill="currentColor" />
                Coba simulator
                <ArrowRight size={16} />
              </a>
              <a href={REGISTER_URL} className="bal-btn line">
                <UserPlus size={16} />
                Daftar dan buka dasbor
              </a>
            </div>
            <p className="close-note">Masih tahap uji coba di Sukoharjo. Angka di situs ini estimasi, bukan penawaran.</p>
          </Reveal>
        </div>
      </section>

      <footer className="site-footer">
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
                <p className="text-xs font-bold tracking-widest uppercase mb-3" style={{ color: '#4C9A74' }}>Kemitraan</p>
                <p className="text-xs leading-relaxed" style={{ color: '#6FA687' }}>
                  Belum ada MoU resmi. Yang dijajaki: Disperinaker Sukoharjo, UMKM binaan uji coba, dan tenan energi inkubator UNS.
                </p>
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
