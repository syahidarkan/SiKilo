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
      if (idx >= words.length && timerRef.current) clearInterval(timerRef.current);
    }, 44);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [active, text]);

  return (
    <span>
      {words.map((word, i) => (
        <span
          key={i}
          style={{
            opacity: i < revealed ? 1 : 0,
            transition: 'opacity 0.1s',
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
    setTimeout(() => setTypingIdx(i), 400);
  }

  return (
    <section className="py-24 md:py-32" style={{ background: 'var(--bg-paper)' }}>
      <div className="max-w-5xl mx-auto px-4">

        {/* Two-column layout: info left, accordion right */}
        <div className="grid md:grid-cols-[1fr_1.6fr] gap-12 md:gap-16 items-start">

          {/* Left — sticky info */}
          <div className="md:sticky md:top-24">
            <span
              className="inline-flex items-center gap-1.5 text-xs font-bold tracking-widest uppercase mb-5 px-3 py-1 rounded-full"
              style={{ background: 'var(--solar-light)', color: 'var(--solar-dark)' }}
            >
              ⚡ FAQ
            </span>
            <h2
              className="text-3xl md:text-4xl font-extrabold leading-tight mb-4"
              style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)', letterSpacing: '-0.03em' }}
            >
              Tanya langsung<br /> Si Kilo
            </h2>
            <p className="text-sm leading-relaxed mb-6" style={{ color: 'var(--metal-mid)' }}>
              Pertanyaan yang sering muncul, dijawab Si Kilo secara langsung.
            </p>

            {/* Si Kilo avatar card */}
            <div
              className="inline-flex items-center gap-3 px-4 py-3 rounded-2xl"
              style={{ background: 'var(--bg-surface)', border: '1.5px solid var(--border-soft)' }}
            >
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center text-lg font-bold shrink-0"
                style={{ background: 'linear-gradient(135deg, var(--solar-primary) 0%, var(--eco-primary) 100%)', color: '#fff' }}
              >
                ⚡
              </div>
              <div>
                <p className="text-sm font-bold" style={{ color: 'var(--metal-dark)' }}>Si Kilo</p>
                <p className="text-xs" style={{ color: 'var(--metal-light)' }}>AI Energy Dispatcher</p>
              </div>
              <div className="flex gap-0.5 ml-1">
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    className="block rounded-full"
                    style={{
                      width: 5, height: 5,
                      background: 'var(--eco-primary)',
                      animation: `pulse 1.2s ease-in-out ${d * 0.2}s infinite`,
                    }}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Right — FAQ accordion */}
          <div className="space-y-3">
            {FAQS.map((faq, i) => (
              <div
                key={i}
                className="rounded-2xl overflow-hidden"
                style={{
                  border: `1.5px solid ${openIdx === i ? 'var(--border-medium)' : 'var(--border-soft)'}`,
                  background: openIdx === i ? '#fff' : 'var(--bg-surface)',
                  transition: 'background 0.2s, border-color 0.2s',
                  boxShadow: openIdx === i ? '0 4px 20px -4px rgba(31,41,55,0.08)' : 'none',
                }}
              >
                {/* Question (user bubble) */}
                <button
                  className="w-full flex items-start gap-3 p-4 md:p-5 text-left"
                  onClick={() => handleOpen(i)}
                  aria-expanded={openIdx === i}
                >
                  <div
                    className="w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-xs font-bold"
                    style={{ background: 'var(--border-medium)', color: 'var(--metal-mid)', marginTop: '1px' }}
                  >
                    U
                  </div>
                  <div className="flex-1">
                    <div
                      className="inline-block rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm font-medium text-left"
                      style={{ background: 'var(--border-soft)', color: 'var(--metal-dark)' }}
                    >
                      {faq.q}
                    </div>
                  </div>
                  <svg
                    className="shrink-0 mt-2 transition-transform duration-200"
                    style={{ transform: openIdx === i ? 'rotate(180deg)' : 'rotate(0deg)', color: 'var(--metal-light)' }}
                    width="16" height="16" viewBox="0 0 16 16" fill="none"
                  >
                    <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>

                {/* Answer (Si Kilo bubble) */}
                {openIdx === i && (
                  <div className="px-4 md:px-5 pb-5">
                    <div className="flex items-start gap-3">
                      <div
                        className="w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-sm"
                        style={{
                          background: 'linear-gradient(135deg, var(--solar-primary) 0%, var(--eco-primary) 100%)',
                          color: '#fff',
                          marginTop: '1px',
                          fontSize: '14px',
                        }}
                      >
                        ⚡
                      </div>
                      <div className="flex-1">
                        {typingIdx !== i ? (
                          /* Typing indicator */
                          <div
                            className="inline-flex items-center gap-1.5 rounded-2xl rounded-tl-sm px-4 py-3"
                            style={{ background: 'var(--solar-light)', border: '1px solid var(--border-soft)' }}
                          >
                            {[0, 1, 2].map((d) => (
                              <span
                                key={d}
                                className="block rounded-full"
                                style={{
                                  width: 6, height: 6,
                                  background: 'var(--solar-primary)',
                                  animation: `dot-bounce 0.9s ease-in-out ${d * 0.15}s infinite`,
                                }}
                              />
                            ))}
                          </div>
                        ) : (
                          /* Answer text */
                          <div
                            className="rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed"
                            style={{
                              background: 'var(--solar-light)',
                              border: '1px solid var(--border-soft)',
                              color: 'var(--metal-dark)',
                            }}
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
      </div>

      <style>{`
        @keyframes dot-bounce {
          0%, 80%, 100% { transform: translateY(0); }
          40% { transform: translateY(-5px); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.7); }
        }
      `}</style>
    </section>
  );
}
