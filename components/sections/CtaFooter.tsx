'use client';

export default function CtaFooter() {
  return (
    <>
      {/* ── CTA Section ─────────────────────────────────────────── */}
      <section
        className="py-24 md:py-32 relative overflow-hidden"
        style={{ background: '#0F2820' }}
      >
        {/* Subtle radial glow */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'radial-gradient(ellipse 70% 60% at 50% 100%, rgba(47,191,113,0.12) 0%, transparent 70%)',
          }}
          aria-hidden="true"
        />

        <div className="relative max-w-3xl mx-auto px-4 text-center">
          {/* Si Kilo icon */}
          <div
            className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-8 text-2xl"
            style={{ background: 'rgba(47,191,113,0.15)', border: '1.5px solid rgba(47,191,113,0.25)' }}
          >
            ⚡
          </div>

          <h2
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
            <a
              href="#simulator-section"
              className="inline-flex items-center justify-center gap-2 px-7 py-3.5 rounded-2xl font-bold text-sm transition-all hover:scale-105 active:scale-95"
              style={{
                background: 'var(--eco-primary)',
                color: '#fff',
                boxShadow: '0 8px 28px -8px rgba(47,191,113,0.5)',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M8 1L2 9h6l-2 6L14 7H8L10 1 8 1z" fill="currentColor" />
              </svg>
              Coba Simulator Gratis
            </a>
            <a
              href="mailto:syhd.acan@gmail.com?subject=NOTA LISTRIK - Daftar Early Access"
              className="inline-flex items-center justify-center gap-2 px-7 py-3.5 rounded-2xl font-bold text-sm border transition-all hover:scale-105 active:scale-95"
              style={{
                borderColor: 'rgba(74,222,128,0.4)',
                color: '#4ADE80',
                background: 'transparent',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 4a1 1 0 011-1h10a1 1 0 011 1v8a1 1 0 01-1 1H3a1 1 0 01-1-1V4zm1 0l5 4 5-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Daftar Early Access
            </a>
          </div>

          <p className="mt-7 text-xs" style={{ color: 'rgba(134,239,172,0.55)' }}>
            Tidak perlu kartu kredit · Tidak perlu pasang hardware · Mulai dalam 5 menit
          </p>
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────────── */}
      <footer style={{ background: '#0A1E14' }}>
        <div className="max-w-5xl mx-auto px-4 py-10">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-10">

            {/* Brand */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center text-sm font-bold"
                  style={{ background: 'var(--eco-primary)', color: '#fff' }}
                >
                  ⚡
                </div>
                <span className="font-black text-sm tracking-tight" style={{ color: '#fff' }}>
                  NOTA<span style={{ color: 'var(--eco-primary)' }}>LISTRIK</span>
                </span>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: '#4B7A5E' }}>
                AI Energy Dispatcher &amp; Solar Right-Sizing untuk UMKM Indonesia.
              </p>
            </div>

            {/* Links */}
            <div>
              <p className="text-xs font-bold tracking-widest uppercase mb-3" style={{ color: '#2D6A4F' }}>Produk</p>
              <ul className="space-y-1.5 text-xs" style={{ color: '#4B7A5E' }}>
                {['Nota Listrik Cerdas', 'AI Dispatcher', 'Solar Right-Sizing', 'Energy Credit Scorecard'].map((item) => (
                  <li key={item}>
                    <a href="#simulator-section" className="transition-colors hover:text-green-400">
                      {item}
                    </a>
                  </li>
                ))}
              </ul>
            </div>

            {/* Partnership */}
            <div>
              <p className="text-xs font-bold tracking-widest uppercase mb-3" style={{ color: '#2D6A4F' }}>Didukung Oleh</p>
              <div className="flex flex-wrap gap-1.5">
                {['PLN Icon', 'BRI UMKM', 'Kementerian ESDM', 'UNS Innovation'].map((name) => (
                  <div
                    key={name}
                    className="px-2.5 py-1 rounded-lg text-xs font-semibold"
                    style={{ background: '#0F2820', color: '#2D6A4F', border: '1px solid #162B23' }}
                  >
                    {name}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Divider + copyright */}
          <div
            className="pt-6 flex flex-col md:flex-row items-center justify-between gap-2 text-xs"
            style={{ borderTop: '1px solid #162B23', color: '#2D6A4F' }}
          >
            <span>© 2026 NOTA LISTRIK · UNS Innovation Hackathon · Energy Track Sub-tema C</span>
            <span>Made with ⚡ by Si Kilo</span>
          </div>
        </div>
      </footer>
    </>
  );
}
