'use client';

export default function CtaFooter() {
  return (
    <>
      {/* CTA Section */}
      <section
        className="py-24 md:py-32 relative overflow-hidden"
        style={{ background: 'linear-gradient(145deg, #0F3023 0%, #1A4A35 50%, #0F2820 100%)' }}
      >
        {/* Background solar rays */}
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          {[0, 60, 120, 180, 240, 300].map((deg, i) => (
            <div
              key={i}
              className="absolute"
              style={{
                top: '50%',
                left: '50%',
                width: '200%',
                height: '1px',
                background: 'linear-gradient(90deg, transparent 0%, rgba(255,167,38,0.07) 50%, transparent 100%)',
                transform: `translate(-50%, -50%) rotate(${deg}deg)`,
              }}
            />
          ))}
        </div>

        <div className="relative max-w-4xl mx-auto px-4 text-center">
          {/* Si Kilo mini diorama */}
          <div className="flex justify-center mb-8">
            <svg viewBox="0 0 120 80" width="120" height="80" fill="none" xmlns="http://www.w3.org/2000/svg">
              {/* Ground */}
              <rect x="10" y="60" width="100" height="6" rx="2" fill="#1E4A35" />
              {/* Shop silhouette */}
              <rect x="30" y="38" width="60" height="22" rx="3" fill="#2D6A4F" />
              <polygon points="25,38 60,22 95,38" fill="#22C55E" />
              {/* PV panel */}
              <rect x="40" y="24" width="20" height="12" rx="1.5" fill="#38BDF8" opacity="0.9" />
              <line x1="40" y1="30" x2="60" y2="30" stroke="#0EA5E9" strokeWidth="0.8" />
              <line x1="50" y1="24" x2="50" y2="36" stroke="#0EA5E9" strokeWidth="0.8" />
              {/* Sparkles */}
              <circle cx="68" cy="20" r="2" fill="#FFA726" opacity="0.9">
                <animate attributeName="opacity" values="0.9;0.3;0.9" dur="1.6s" repeatCount="indefinite" />
              </circle>
              <circle cx="80" cy="30" r="1.5" fill="#22C55E" opacity="0.8">
                <animate attributeName="opacity" values="0.8;0.2;0.8" dur="1.2s" begin="0.4s" repeatCount="indefinite" />
              </circle>
              <circle cx="35" cy="32" r="1" fill="#38BDF8" opacity="0.7">
                <animate attributeName="opacity" values="0.7;0.1;0.7" dur="2s" begin="0.8s" repeatCount="indefinite" />
              </circle>
              {/* Si Kilo body */}
              <circle cx="62" cy="52" r="5" fill="#FFA726" />
              <circle cx="62" cy="44" r="4" fill="#FFD580" />
              {/* Eyes */}
              <circle cx="60.5" cy="43.5" r="1" fill="#1F2937" />
              <circle cx="63.5" cy="43.5" r="1" fill="#1F2937" />
              {/* Smile */}
              <path d="M60 45.5 Q62 47 64 45.5" stroke="#1F2937" strokeWidth="0.7" strokeLinecap="round" fill="none" />
              {/* Bolt badge */}
              <text x="59.5" y="54" fontSize="5" fill="#fff" fontWeight="bold">⚡</text>
            </svg>
          </div>

          <h2
            className="text-3xl md:text-5xl font-bold mb-6 leading-tight"
            style={{ color: '#fff', fontFamily: 'var(--font-display)' }}
          >
            Tagihan lebih kecil.<br />
            <span style={{ color: '#4ADE80' }}>Mimpi PLTS makin dekat.</span>
          </h2>
          <p className="text-base md:text-lg mb-10 max-w-xl mx-auto" style={{ color: '#A7F3D0' }}>
            Mulai gratis dengan Nota Listrik Cerdas. Upgrade ke AI Dispatcher kapan saja kamu siap.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="#simulator-section"
              className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-2xl font-bold text-base transition-all hover:scale-105 active:scale-95"
              style={{
                background: 'linear-gradient(135deg, #FFA726 0%, #F59E0B 100%)',
                color: '#fff',
                boxShadow: '0 8px 32px -8px rgba(255,167,38,0.5)',
              }}
            >
              ⚡ Coba Simulator Gratis
            </a>
            <a
              href="mailto:syhd.acan@gmail.com?subject=NOTA LISTRIK - Daftar Early Access"
              className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-2xl font-bold text-base border transition-all hover:scale-105 active:scale-95"
              style={{ borderColor: '#4ADE80', color: '#4ADE80', background: 'transparent' }}
            >
              📋 Daftar Early Access
            </a>
          </div>

          <p className="mt-6 text-xs" style={{ color: '#6EE7B7' }}>
            Tidak perlu kartu kredit · Tidak perlu pasang hardware · Mulai dalam 5 menit
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer>
        {/* Wave 1 */}
        <div style={{ background: '#1E3A2F', lineHeight: 0 }}>
          <svg viewBox="0 0 1440 48" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" style={{ display: 'block', width: '100%', height: '48px' }}>
            <path d="M0,32 C360,0 1080,48 1440,16 L1440,0 L0,0 Z" fill="#0F3023" />
          </svg>
        </div>
        <div style={{ background: '#1E3A2F' }} className="px-4 pt-12 pb-8">
          <div className="max-w-5xl mx-auto">
            {/* Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-10 mb-10">
              {/* Brand */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xl font-black tracking-tight" style={{ color: '#fff' }}>NOTA</span>
                  <span className="text-xl font-black tracking-tight" style={{ color: '#FFA726' }}>LISTRIK</span>
                  <span className="text-lg">⚡</span>
                </div>
                <p className="text-xs leading-relaxed" style={{ color: '#6EE7B7' }}>
                  AI Energy Dispatcher &amp; Solar Right-Sizing untuk UMKM Indonesia. Hemat energi, raih PLTS.
                </p>
              </div>

              {/* Links */}
              <div>
                <p className="text-xs font-bold tracking-widest uppercase mb-3" style={{ color: '#4ADE80' }}>Produk</p>
                <ul className="space-y-2 text-xs" style={{ color: '#A7F3D0' }}>
                  {['Nota Listrik Cerdas', 'AI Dispatcher', 'Solar Right-Sizing', 'Energy Credit Scorecard'].map((item) => (
                    <li key={item}><a href="#simulator-section" className="hover:text-white transition-colors">{item}</a></li>
                  ))}
                </ul>
              </div>

              {/* Partnership logos (placeholder chips) */}
              <div>
                <p className="text-xs font-bold tracking-widest uppercase mb-3" style={{ color: '#4ADE80' }}>Didukung Oleh</p>
                <div className="flex flex-wrap gap-2">
                  {['PLN icon', 'BRI UMKM', 'Kementerian ESDM', 'UNS Innovation'].map((name) => (
                    <div
                      key={name}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold"
                      style={{ background: '#162B23', color: '#6EE7B7', border: '1px solid #2D4A3E' }}
                    >
                      {name}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Wave 2 */}
            <div style={{ lineHeight: 0, margin: '0 -1rem' }}>
              <svg viewBox="0 0 1440 24" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" style={{ display: 'block', width: '100%', height: '24px' }}>
                <path d="M0,16 C480,0 960,24 1440,8 L1440,24 L0,24 Z" fill="#162B23" />
              </svg>
            </div>

            <div style={{ background: '#162B23', margin: '0 -1rem', padding: '1.5rem 1rem 0' }}>
              {/* Wave 3 */}
              <div style={{ lineHeight: 0, margin: '0 -1rem' }}>
                <svg viewBox="0 0 1440 20" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" style={{ display: 'block', width: '100%', height: '20px' }}>
                  <path d="M0,12 C360,0 1080,20 1440,6 L1440,20 L0,20 Z" fill="#0F1E18" />
                </svg>
              </div>
              <div style={{ background: '#0F1E18', margin: '0 -1rem', padding: '1.25rem 1rem' }}>
                <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-3 text-xs" style={{ color: '#4ADE80' }}>
                  <span>© 2026 NOTA LISTRIK · UNS Innovation Hackathon · Energy Track Sub-tema C</span>
                  <span style={{ color: '#2D6A4F' }}>Made with ⚡ &amp; ☀️ by Si Kilo</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
}
