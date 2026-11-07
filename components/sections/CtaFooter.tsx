'use client';

import Image from 'next/image';
import { ArrowRight, ArrowUp, UserPlus, Zap } from 'lucide-react';
import { DASHBOARD_URL, REGISTER_URL } from '@/lib/waskita';
import Reveal from '@/components/Reveal';
import { LogoMark } from '@/components/Logo';

const EXPLORE_LINKS = [
  { label: 'Cerita', href: '#sehari' },
  { label: 'Simulator', href: '#simulator-section' },
  { label: 'Fitur', href: '#fitur' },
  { label: 'Tanya jawab', href: '#faq' },
];

const PRODUCT_LINKS = [
  { label: 'Pembacaan beban', href: '#fitur' },
  { label: 'Penjadwalan mesin', href: '#fitur' },
  { label: 'Simulator PLTS', href: '#simulator-section' },
  { label: 'Rapor kelayakan', href: '#fitur' },
];

export default function CtaFooter() {
  return (
    <>
      <section className="close" aria-labelledby="h-cta">
        <div className="close-dots" aria-hidden="true" />
        <div className="sheet-w">
          <Reveal>
            <div className="sh-mark" style={{ justifyContent: 'center' }}>
              <b>05</b>
              <span>Mulai</span>
            </div>
            <h2 id="h-cta" className="close-title">
              Hitung dulu, <em>pasang kemudian.</em>
            </h2>
            <p className="close-lead">
              Masukkan daya PLN dan mesin di usaha Anda. Perkiraan ukuran PLTS dan waktu balik modal langsung muncul di simulator.
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
            <p className="close-note">Program ini masih tahap uji coba di Sukoharjo. Semua angka di situs ini berupa perkiraan, bukan penawaran.</p>
          </Reveal>
        </div>
      </section>

      <footer className="site-footer">
        <div className="sf-body">
          <div className="sheet-w">
            <div className="sf-grid">
              <div>
                <a className="sf-brand" href="#top">
                  <LogoMark size={40} />
                  WASKITA
                </a>
                <p className="sf-tag">Membaca listrik tiap mesin, menggeser jadwalnya ke jam matahari, dan menyiapkan rapor untuk bank.</p>
              </div>

              <nav className="sf-col" aria-label="Jelajahi">
                <h3>Jelajahi</h3>
                <ul>
                  {EXPLORE_LINKS.map(({ label, href }) => (
                    <li key={label}><a href={href}>{label}</a></li>
                  ))}
                </ul>
              </nav>

              <nav className="sf-col" aria-label="Produk">
                <h3>Produk</h3>
                <ul>
                  {PRODUCT_LINKS.map(({ label, href }) => (
                    <li key={label}><a href={href}>{label}</a></li>
                  ))}
                  <li><a href={DASHBOARD_URL}>Masuk ke dasbor</a></li>
                </ul>
              </nav>

              <div className="sf-col">
                <h3>Calon mitra</h3>
                <ul className="sf-partners" aria-label="Calon mitra">
                  <li>
                    <Image src="/logos/sukoharjo.svg" alt="Lambang Kabupaten Sukoharjo" width={85} height={108} unoptimized />
                    <span>Disperinaker<br />Sukoharjo</span>
                  </li>
                </ul>
              </div>
            </div>

            <div className="sf-word" aria-hidden="true">WASKITA</div>
          </div>
          <div className="sf-bar">
            <div className="sheet-w" style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '10px 24px', width: '100%' }}>
              <span className="sf-event">
                <span className="sf-logo">
                  <Image src="/uns-innovation-hackathon.png" alt="UNS Innovation Hackathon" width={1811} height={479} sizes="160px" />
                </span>
                <span>© 2026 WASKITA · Energy Track Sub-tema C</span>
              </span>
              <ul className="sf-inst" aria-label="Logo institusi terkait">
                <li>
                  <Image src="/logos/kemdikbud.png" alt="Tut Wuri Handayani, logo Kementerian Pendidikan" width={520} height={527} />
                </li>
                <li>
                  <Image className="sf-on-light" src="/logos/lpdp.png" alt="LPDP, Lembaga Pengelola Dana Pendidikan" width={720} height={346} />
                  <Image className="sf-on-dark" src="/logos/lpdp-white.png" alt="" aria-hidden="true" width={720} height={346} />
                </li>
                <li>
                  <Image src="/logos/lppm-uns.png" alt="LPPM Universitas Sebelas Maret" width={300} height={238} />
                </li>
                <li>
                  <Image src="/logos/logo-s.png" alt="Logo gelombang biru dan jingga" width={520} height={559} />
                </li>
              </ul>
              <a href="#top">Kembali ke atas <ArrowUp size={13} /></a>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
}
