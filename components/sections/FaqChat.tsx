'use client';

import { useState, useEffect, useRef } from 'react';

const FAQS = [
  {
    q: 'Apa itu NOTA LISTRIK dan kenapa saya butuh ini?',
    a: 'NOTA LISTRIK adalah AI Energy Dispatcher yang membantu usahamu membaca tagihan listrik seperti akuntan, mengelola jadwal mesin seperti manajer, dan menyiapkan rapor kelayakan PLTS untuk bank. Kalau tagihan listrikmu lebih dari Rp500.000/bulan, kamu butuh ini.',
  },
  {
    q: 'Bagaimana Si Kilo mendeteksi mesin yang boros?',
    a: 'Si Kilo menggunakan teknologi NILM (Non-Intrusive Load Monitoring) — tanpa perlu pasang sensor di tiap mesin. Cukup satu titik pantau di panel utama, Si Kilo "membaca" sidik jari daya setiap mesin dari pola arus listriknya.',
  },
  {
    q: 'Berapa lama sampai balik modal PLTS?',
    a: 'Rata-rata UMKM binaan kami mencapai break-even dalam 2.8–4.2 tahun. Dengan AI Dispatcher yang mengoptimalkan pemakaian saat sinar matahari paling terik, payback period bisa lebih pendek 20–30% dibanding instalasi PLTS konvensional.',
  },
  {
    q: 'Apakah datanya bisa dipakai untuk pengajuan pinjaman bank?',
    a: 'Ya! Energy Credit Scorecard dari NOTA LISTRIK sudah diformat sesuai standar penilaian kelayakan green financing. Data konsumsi terukur, proyeksi penghematan, dan PBP tersaji dalam laporan yang siap dilampirkan ke Bank BRI, BNI, atau lembaga pembiayaan UMKM lainnya.',
  },
];

function WordReveal({ text, active }: { text: string; active: boolean }) {
  const [revealed, setRevealed] = useState(0);
  const words = text.split(' ');
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!active) { setRevealed(0); return; }
    setRevealed(0);
    let idx = 0;
    timerRef.current = setInterval(() => {
      idx++;
      setRevealed(idx);
      if (idx >= words.length) {
        if (timerRef.current) clearInterval(timerRef.current);
      }
    }, 48);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [active, text]);

  return (
    <span>
      {words.map((word, i) => (
        <span
          key={i}
          style={{
            opacity: i < revealed ? 1 : 0,
            transition: 'opacity 0.12s',
            marginRight: '0.25em',
            display: 'inline-block',
          }}
        >
          {word}
        </span>
      ))}
    </span>
  );
}

export default function FaqChat() {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const [typingIdx, setTypingIdx] = useState<number | null>(null);

  function handleOpen(i: number) {
    if (openIdx === i) { setOpenIdx(null); setTypingIdx(null); return; }
    setOpenIdx(i);
    setTypingIdx(null);
    setTimeout(() => setTypingIdx(i), 420);
  }

  return (
    <section className="py-20 md:py-28" style={{ background: 'var(--bg-paper)' }}>
      <div className="max-w-2xl mx-auto px-4">
        <div className="text-center mb-14">
          <span className="inline-block text-xs font-bold tracking-widest uppercase mb-3" style={{ color: 'var(--eco-primary)' }}>
            FAQ
          </span>
          <h2 className="text-3xl md:text-4xl font-bold mb-3" style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)' }}>
            Tanya langsung Si Kilo
          </h2>
          <p className="text-sm" style={{ color: 'var(--metal-mid)' }}>
            Pertanyaan yang sering muncul, dijawab Si Kilo.
          </p>
        </div>

        <div className="space-y-4">
          {FAQS.map((faq, i) => (
            <div key={i} className="rounded-2xl overflow-hidden" style={{ border: '1.5px solid var(--border-soft)', background: 'var(--bg-surface)' }}>
              {/* Question bubble (user) */}
              <button
                className="w-full flex items-start gap-3 p-4 md:p-5 text-left"
                onClick={() => handleOpen(i)}
                aria-expanded={openIdx === i}
              >
                {/* User avatar */}
                <div
                  className="w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-xs font-bold"
                  style={{ background: 'var(--eco-primary)', color: '#fff', marginTop: '2px' }}
                >
                  U
                </div>
                <div className="flex-1">
                  <div
                    className="inline-block rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm font-medium"
                    style={{ background: 'var(--border-soft)', color: 'var(--metal-dark)' }}
                  >
                    {faq.q}
                  </div>
                </div>
                <svg
                  className="shrink-0 mt-2 transition-transform"
                  style={{ transform: openIdx === i ? 'rotate(180deg)' : 'rotate(0deg)', color: 'var(--metal-light)' }}
                  width="16" height="16" viewBox="0 0 16 16" fill="none"
                >
                  <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              {/* Answer (Si Kilo) */}
              {openIdx === i && (
                <div className="px-4 md:px-5 pb-5">
                  <div className="flex items-start gap-3">
                    {/* Si Kilo avatar */}
                    <div
                      className="w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-sm font-bold"
                      style={{ background: 'linear-gradient(135deg, var(--solar-primary) 0%, var(--eco-primary) 100%)', color: '#fff', marginTop: '2px' }}
                    >
                      ⚡
                    </div>
                    <div className="flex-1">
                      {/* Typing indicator or answer */}
                      {typingIdx !== i ? (
                        <div
                          className="inline-flex items-center gap-1 rounded-2xl rounded-tl-sm px-4 py-2.5"
                          style={{ background: '#FFF3CD', border: '1px solid #FDE68A' }}
                        >
                          {[0, 1, 2].map((d) => (
                            <span
                              key={d}
                              className="block rounded-full"
                              style={{
                                width: 6, height: 6,
                                background: 'var(--solar-primary)',
                                animation: `bounce 0.9s ease-in-out ${d * 0.15}s infinite`,
                              }}
                            />
                          ))}
                        </div>
                      ) : (
                        <div
                          className="rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed"
                          style={{ background: '#FFF8EC', border: '1px solid #FDE68A', color: 'var(--metal-dark)' }}
                        >
                          <WordReveal text={faq.a} active={typingIdx === i} />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); }
          40% { transform: translateY(-5px); }
        }
      `}</style>
    </section>
  );
}
