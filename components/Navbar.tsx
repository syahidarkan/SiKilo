'use client';

import { useState, useEffect } from 'react';

const NAV_LINKS = [
  { label: 'Masalah', href: '#masalah' },
  { label: 'Fitur',   href: '#fitur' },
  { label: 'Cara Kerja', href: '#cara-kerja' },
  { label: 'FAQ',     href: '#faq' },
];

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 48);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        transition: 'background 0.25s, box-shadow 0.25s',
        background: scrolled ? 'rgba(251,249,244,0.92)' : 'rgba(251,249,244,0)',
        backdropFilter: scrolled ? 'blur(14px)' : 'none',
        WebkitBackdropFilter: scrolled ? 'blur(14px)' : 'none',
        boxShadow: scrolled ? '0 1px 0 var(--border-soft)' : 'none',
      }}
    >
      <nav
        style={{
          maxWidth: 1200,
          margin: '0 auto',
          padding: '0 24px',
          height: 64,
          display: 'flex',
          alignItems: 'center',
          gap: 0,
        }}
      >
        {/* ── Logo ─────────────────────────────────────────────── */}
        <a
          href="#top"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 9,
            textDecoration: 'none',
            flex: '0 0 auto',
            marginRight: 32,
          }}
        >
          <span
            style={{
              width: 30,
              height: 30,
              borderRadius: 9,
              background: 'var(--eco-primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <svg width="17" height="17" viewBox="0 0 17 17" fill="none">
              <path d="M9.5 2L4.5 9.5h5.5l-2.5 5.5L14 7.5H8.5L9.5 2z" fill="white" strokeLinejoin="round" />
            </svg>
          </span>
          <span
            style={{
              fontWeight: 800,
              fontSize: 14,
              letterSpacing: '-0.02em',
              color: 'var(--metal-dark)',
              lineHeight: 1,
            }}
          >
            NOTA<br />
            <span style={{ color: 'var(--eco-primary)' }}>LISTRIK</span>
          </span>
        </a>

        {/* ── Nav links — desktop ─────────────────────────────── */}
        <div
          style={{
            display: 'flex',
            gap: 2,
            flex: 1,
            justifyContent: 'center',
          }}
          className="nav-links-desktop"
        >
          {NAV_LINKS.map(({ label, href }) => (
            <NavLink key={label} label={label} href={href} />
          ))}
        </div>

        {/* ── Right actions ─────────────────────────────────────── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: '0 0 auto', marginLeft: 32 }}>
          <a
            href="#masuk"
            style={{
              padding: '7px 15px',
              borderRadius: 9,
              fontSize: 14,
              fontWeight: 600,
              color: 'var(--metal-mid)',
              textDecoration: 'none',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-surface)'; (e.currentTarget as HTMLElement).style.color = 'var(--metal-dark)'; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = 'var(--metal-mid)'; }}
          >
            Masuk
          </a>
          <a
            href="#coba"
            style={{
              padding: '8px 18px',
              borderRadius: 10,
              fontSize: 14,
              fontWeight: 700,
              background: 'var(--eco-primary)',
              color: '#fff',
              textDecoration: 'none',
              transition: 'background 0.15s',
              whiteSpace: 'nowrap',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--eco-hover)'; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'var(--eco-primary)'; }}
          >
            Mulai Gratis
          </a>

          {/* hamburger — only on mobile */}
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="Menu"
            style={{
              display: 'none',
              width: 36,
              height: 36,
              borderRadius: 8,
              border: '1.5px solid var(--border-soft)',
              background: 'transparent',
              cursor: 'pointer',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 0,
            }}
            className="hamburger-btn"
          >
            <svg width="18" height="12" viewBox="0 0 18 12" fill="none">
              <rect y="0" width="18" height="2" rx="1" fill="var(--metal-dark)" />
              <rect y="5" width="13" height="2" rx="1" fill="var(--metal-dark)" />
              <rect y="10" width="18" height="2" rx="1" fill="var(--metal-dark)" />
            </svg>
          </button>
        </div>
      </nav>

      {/* ── Mobile dropdown ─────────────────────────────────────── */}
      {menuOpen && (
        <div
          style={{
            background: 'rgba(251,249,244,0.97)',
            backdropFilter: 'blur(14px)',
            borderTop: '1px solid var(--border-soft)',
            padding: '8px 24px 16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
          }}
        >
          {NAV_LINKS.map(({ label, href }) => (
            <a
              key={label}
              href={href}
              onClick={() => setMenuOpen(false)}
              style={{
                padding: '10px 12px',
                borderRadius: 8,
                fontSize: 15,
                fontWeight: 500,
                color: 'var(--metal-dark)',
                textDecoration: 'none',
              }}
            >
              {label}
            </a>
          ))}
        </div>
      )}

      <style>{`
        @media (max-width: 768px) {
          .nav-links-desktop { display: none !important; }
          .hamburger-btn { display: flex !important; }
        }
      `}</style>
    </header>
  );
}

function NavLink({ label, href }: { label: string; href: string }) {
  return (
    <a
      href={href}
      style={{
        padding: '6px 14px',
        borderRadius: 8,
        fontSize: 14,
        fontWeight: 500,
        color: 'var(--metal-mid)',
        textDecoration: 'none',
        transition: 'background 0.12s, color 0.12s',
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLElement).style.background = 'var(--bg-surface)';
        (e.currentTarget as HTMLElement).style.color = 'var(--metal-dark)';
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLElement).style.background = 'transparent';
        (e.currentTarget as HTMLElement).style.color = 'var(--metal-mid)';
      }}
    >
      {label}
    </a>
  );
}
