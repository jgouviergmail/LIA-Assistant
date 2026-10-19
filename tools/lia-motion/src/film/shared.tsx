import React, { useEffect, useRef, type CSSProperties, type ReactNode } from 'react';
import { Easing, Img, interpolate, spring, staticFile } from 'remotion';
import { Sparkles } from 'lucide-react';
import { EyesFace } from '@/components/eyes/EyesFace';
import { resolvePose } from '@/components/eyes/rig/poses';
import { createRigWriter } from '@/components/eyes/rig/apply';
import type { EyeExpression } from '@/components/eyes/expression-engine';
import '@/styles/eyes.css';
import './shared.css';

export type SceneProps = { frame: number };
export const colors = {
  ink: '#15263d', muted: '#62738a', blue: '#347cf6', cyan: '#3bd2e6',
  violet: '#8162e8', paper: '#f7f9fe', line: '#dce5f1', night: '#080e20',
};
export const ease = (frame: number, start: number, end: number) => interpolate(
  frame, [start, end], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(.2, .85, .22, 1) },
);
export const uiSpring = (frame: number, start = 0) => spring({
  frame: frame - start, fps: 60, config: { damping: 24, stiffness: 145, mass: 1.1 },
});

export function FilmCursor({ x, y, pressed = false }: { x: number; y: number; pressed?: boolean }) {
  return <div className="film-cursor" style={{ left: x, top: y, transform: `scale(${pressed ? .84 : 1})` }}>
    {pressed && <span className="film-cursor-ring" />}
    <svg width="42" height="53" viewBox="0 0 42 53"><path d="M5 3 5 39 15 30 23 47 30 43 22 27 36 27Z" fill="#fff" stroke="#142d53" strokeWidth="3" strokeLinejoin="round" /></svg>
  </div>;
}

export function SceneCaption({ kicker, title, detail }: { kicker?: string; title: ReactNode; detail?: ReactNode }) {
  return <header className="film-scene-caption">
    {kicker && <div className="film-kicker">{kicker}</div>}
    <h2>{title}</h2>{detail && <p>{detail}</p>}
  </header>;
}

export function NativeWindow({ children, title, style, className = '' }: { children: ReactNode; title?: string; style?: CSSProperties; className?: string }) {
  return <section className={`film-native-window ${className}`} style={style}>
    {title && <header className="film-window-title"><Sparkles size={24} /><span>{title}</span><span className="film-window-account">LIA</span></header>}
    {children}
  </section>;
}

export function FilmBrand({ size = 44 }: { size?: number }) {
  return <div className="film-brand" style={{ fontSize: size }}><Img src={staticFile('film/icon.svg')} style={{ width: size * 1.05, height: size * 1.05 }} /><strong>LIA</strong></div>;
}

/** Native body/face; one deterministic film clock, no application account or autonomous idle. */
export function FilmBip({ frame, size = 340, expression = 'attentive', gazeX = -.25 }: {
  frame: number; size?: number; expression?: EyeExpression; gazeX?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const textures = {
    '--spirit-body-url': 'bip-body.webp', '--spirit-eye-url': 'eye.webp',
    '--spirit-eye-right-url': 'eye-right.webp', '--spirit-iris-url': 'iris.webp',
    '--spirit-sclera-url': 'sclera-mask.webp', '--spirit-sclera-right-url': 'sclera-mask-right.webp',
  };
  const textureRules = Object.entries(textures).map(([key, file]) => `${key}:url("${staticFile(`film/${file}`)}") !important`).join(';');
  useEffect(() => {
    const element = host.current?.querySelector<HTMLElement>('.lia-eyes');
    if (!element) return;
    const pose = { ...resolvePose(expression, 'billes') };
    pose.gazeX = gazeX;
    pose.gazeY = -.05;
    pose.headYaw = gazeX * .28;
    pose.tilt = gazeX * 2;
    const local = frame % 480;
    const blink = Math.max(0, 1 - Math.abs(local - 207) / 7);
    pose.blinkL = blink;
    pose.blinkR = blink;
    const writer = createRigWriter(element);
    writer.write(pose);
    return () => writer.dispose();
  }, [frame, expression, gazeX]);
  return <div ref={host} className="film-bip" style={{ width: size, height: size }}>
    <style>{`.film-bip .lia-spirit-companion[data-spirit-companion='male']{${textureRules}}`}</style>
    <div style={{ transform: `scale(${size / 166.4})`, transformOrigin: 'top left' }}>
      <EyesFace styleId="bip" variant="male" expression={expression} gaze={null} size="xl" animate={false} staticPose life={false} allowSleep={false} />
    </div>
  </div>;
}
