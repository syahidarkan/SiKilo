'use client';

import dynamic from 'next/dynamic';

const HeroDioramaScene = dynamic(
  () => import('@/components/3d/HeroDioramaScene'),
  { ssr: false },
);

export default function HeroDioramaWrapper() {
  return <HeroDioramaScene />;
}
