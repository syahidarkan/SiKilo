import Link from 'next/link';

export default function Home() {
  return (
    <main
      className="flex flex-col items-center justify-center min-h-screen gap-8 px-6"
      style={{ background: 'var(--bg-paper)' }}
    >
      <div className="text-center max-w-xl">
        <span
          className="kicker block mb-3"
          style={{ color: 'var(--eco-primary)' }}
        >
          UNS Innovation Hackathon 2026 · Energy Track C
        </span>
        <h1
          className="heading text-4xl md:text-5xl mb-4"
          style={{ color: 'var(--metal-dark)' }}
        >
          NOTA LISTRIK
        </h1>
        <p
          className="text-base leading-relaxed"
          style={{ color: 'var(--metal-mid)' }}
        >
          Platform AI Energy Dispatcher &amp; Solar Right-Sizing untuk Sentra UMKM Indonesia
        </p>
      </div>

      <Link
        href="/mascot-test"
        className="inline-flex items-center gap-2 px-6 py-3 rounded-full font-semibold text-white transition-all duration-200 hover:scale-105 active:scale-95"
        style={{
          background: 'var(--solar-primary)',
          boxShadow: 'var(--shadow-hover)',
        }}
      >
        <span>Lihat Si Kilo — Test Bench</span>
        <span>→</span>
      </Link>
    </main>
  );
}
