import Navbar from '@/components/Navbar';
import HeroDioramaWrapper from '@/components/3d/HeroDioramaWrapper';
import StoryScene from '@/components/story/StoryScene';
import SimulatorSection from '@/components/sections/SimulatorSection';
import FeatureCards from '@/components/sections/FeatureCards';
import FaqChat from '@/components/sections/FaqChat';
import CtaFooter from '@/components/sections/CtaFooter';

export default function Home() {
  return (
    <main id="top" style={{ background: 'var(--bg-paper)' }}>
      <Navbar />
      {/* ── Hero: 500vh sticky scroll-track ─────────────────────── */}
      <div id="scroll-track" className="relative w-full" style={{ height: '500vh' }}>
        <div className="sticky top-0 w-full h-screen overflow-hidden">
          <HeroDioramaWrapper />
        </div>
      </div>

      {/* ── Satu hari di Laundry Barokah: scroll-story isometrik ── */}
      <section id="sehari" aria-label="Satu hari di Laundry Barokah">
        <StoryScene />
      </section>

      {/* ── Simulator Right-Sizing ─────────────────────────────── */}
      <SimulatorSection />

      {/* ── Feature Cards (clothesline) ────────────────────────── */}
      <FeatureCards />

      {/* ── FAQ Chat ──────────────────────────────────────────── */}
      <FaqChat />

      {/* ── CTA + Footer ──────────────────────────────────────── */}
      <CtaFooter />
    </main>
  );
}
