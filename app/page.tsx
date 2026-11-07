import Navbar from '@/components/Navbar';
import StoryScene from '@/components/story/StoryScene';
import SimulatorSection from '@/components/sections/SimulatorSection';
import FeatureCards from '@/components/sections/FeatureCards';
import FaqChat from '@/components/sections/FaqChat';
import CtaFooter from '@/components/sections/CtaFooter';

export default function Home() {
  return (
    <main id="top" style={{ background: 'var(--bg-paper)' }}>
      <Navbar />
      {/* ── Satu hari di Laundry Barokah: scroll-story isometrik ── */}
      <section id="sehari" aria-label="Satu hari di Laundry Barokah">
        <StoryScene />
      </section>

      <div className="sheet">
        {/* ── Simulator Right-Sizing ─────────────────────────────── */}
        <SimulatorSection />

        {/* ── Feature Cards (clothesline) ────────────────────────── */}
        <FeatureCards />

        {/* ── FAQ Chat ──────────────────────────────────────────── */}
        <FaqChat />

        {/* ── CTA + Footer ──────────────────────────────────────── */}
        <CtaFooter />
      </div>
    </main>
  );
}
