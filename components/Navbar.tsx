'use client';

import { useEffect, useRef, useState } from 'react';
import { LogIn, Menu, X, Zap } from 'lucide-react';
import { DASHBOARD_URL } from '@/lib/waskita';

const NAV_LINKS = [
  { label: 'Cerita', id: 'sehari' },
  { label: 'Simulator', id: 'simulator-section' },
  { label: 'Fitur', id: 'fitur' },
  { label: 'FAQ', id: 'faq' },
];

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [active, setActive] = useState<string>('sehari');
  const headerRef = useRef<HTMLElement>(null);

  // Scrolled state + page progress, in one rAF-throttled listener.
  useEffect(() => {
    let queued = false;
    const update = () => {
      queued = false;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const p = max > 0 ? Math.min(1, window.scrollY / max) : 0;
      headerRef.current?.style.setProperty('--p', p.toFixed(4));
      setScrolled(window.scrollY > 48);
    };
    const onScroll = () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);

  // Scrollspy: the section crossing the middle of the viewport is the active one.
  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) setActive(e.target.id);
        });
      },
      { rootMargin: '-45% 0px -50% 0px' },
    );
    NAV_LINKS.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (el) io.observe(el);
    });
    return () => io.disconnect();
  }, []);

  // Escape closes the mobile menu.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenuOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  return (
    <header ref={headerRef} className={`nav ${scrolled || menuOpen ? 'nav-solid' : ''}`}>
      <nav className="nav-bar" aria-label="Navigasi utama">
        <a href="#top" className="nav-logo" onClick={() => setMenuOpen(false)}>
          <span className="nav-mark">
            <Zap size={17} strokeWidth={2.6} fill="currentColor" />
          </span>
          <span className="nav-word">
            WAS<span>KITA</span>
          </span>
        </a>

        <div className="nav-links">
          {NAV_LINKS.map(({ label, id }) => (
            <a
              key={id}
              href={`#${id}`}
              className={`nav-link ${active === id ? 'on' : ''}`}
              aria-current={active === id ? 'true' : undefined}
            >
              {label}
            </a>
          ))}
        </div>

        <div className="nav-right">
          <a href={DASHBOARD_URL} className="nav-link inline-flex items-center gap-1.5" title="Masuk ke dasbor WASKITA">
            <LogIn size={15} /> Masuk
          </a>
          <a href="#simulator-section" className="nav-cta">
            Coba Simulator
          </a>
          <button
            type="button"
            className="nav-burger"
            aria-label={menuOpen ? 'Tutup menu' : 'Buka menu'}
            aria-expanded={menuOpen}
            aria-controls="nav-sheet"
            onClick={() => setMenuOpen((o) => !o)}
          >
            {menuOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </nav>

      <div id="nav-sheet" className={`nav-sheet ${menuOpen ? 'open' : ''}`}>
        <div className="nav-sheet-in">
          {NAV_LINKS.map(({ label, id }) => (
            <a
              key={id}
              href={`#${id}`}
              className={`nav-sheet-link ${active === id ? 'on' : ''}`}
              tabIndex={menuOpen ? 0 : -1}
              onClick={() => setMenuOpen(false)}
            >
              {label}
            </a>
          ))}
          <a
            href="#simulator-section"
            className="nav-sheet-cta"
            tabIndex={menuOpen ? 0 : -1}
            onClick={() => setMenuOpen(false)}
          >
            Coba Simulator
          </a>
          <a
            href={DASHBOARD_URL}
            className="nav-sheet-link"
            tabIndex={menuOpen ? 0 : -1}
            onClick={() => setMenuOpen(false)}
          >
            Masuk Dasbor
          </a>
        </div>
      </div>

      {/* Page progress, like a meter filling up */}
      <div className="nav-progress" aria-hidden="true">
        <i />
      </div>
    </header>
  );
}
