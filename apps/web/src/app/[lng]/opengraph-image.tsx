import { ImageResponse } from 'next/og';

export const runtime = 'edge';
export const alt = 'LIA — Assistant IA personnel intelligent';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default async function Image({ params }: { params: Promise<{ lng: string }> }) {
  const { lng } = await params;

  const taglines: Record<string, { line1: string; line2: string; line3: string; sub: string }> = {
    fr: { line1: 'Ta vie.', line2: 'Ton IA.', line3: 'Tes règles.', sub: 'Assistant IA personnel intelligent' },
    en: { line1: 'Your life.', line2: 'Your AI.', line3: 'Your rules.', sub: 'Intelligent personal AI assistant' },
    es: { line1: 'Tu vida.', line2: 'Tu IA.', line3: 'Tus reglas.', sub: 'Asistente IA personal inteligente' },
    de: { line1: 'Dein Leben.', line2: 'Deine KI.', line3: 'Deine Regeln.', sub: 'Intelligenter persönlicher KI-Assistent' },
    it: { line1: 'La tua vita.', line2: 'La tua IA.', line3: 'Le tue regole.', sub: 'Assistente IA personale intelligente' },
    zh: { line1: '你的生活。', line2: '你的AI。', line3: '你的规则。', sub: '智能个人AI助手' },
  };

  const t = taglines[lng] || taglines.fr;

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #1e1b4b 0%, #2563eb 50%, #7c3aed 100%)',
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        {/* Logo circle */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 80,
            height: 80,
            borderRadius: 20,
            background: 'rgba(255,255,255,0.15)',
            marginBottom: 32,
          }}
        >
          <div style={{ fontSize: 40, fontWeight: 700, color: 'white' }}>L</div>
        </div>

        {/* Tagline */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 4,
          }}
        >
          <div style={{ fontSize: 56, fontWeight: 800, color: 'white', lineHeight: 1.2 }}>
            {t.line1} {t.line2} {t.line3}
          </div>
        </div>

        {/* Subtitle */}
        <div
          style={{
            fontSize: 24,
            color: 'rgba(255,255,255,0.7)',
            marginTop: 20,
          }}
        >
          {t.sub}
        </div>

        {/* BETA badge */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginTop: 24,
            padding: '8px 20px',
            borderRadius: 9999,
            background: 'rgba(255,255,255,0.15)',
            color: 'white',
            fontSize: 16,
            fontWeight: 600,
          }}
        >
          BETA
        </div>
      </div>
    ),
    { ...size }
  );
}
