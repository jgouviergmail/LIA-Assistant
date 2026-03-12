'use client';

import { useEffect, useRef } from 'react';

const NODES = [
  { cx: 10, cy: 15, r: 2, delay: 0 },
  { cx: 25, cy: 8, r: 1.5, delay: 1 },
  { cx: 40, cy: 20, r: 2.5, delay: 2 },
  { cx: 55, cy: 10, r: 1.8, delay: 0.5 },
  { cx: 70, cy: 18, r: 2, delay: 1.5 },
  { cx: 85, cy: 12, r: 1.5, delay: 3 },
  { cx: 15, cy: 40, r: 2, delay: 2.5 },
  { cx: 30, cy: 35, r: 1.8, delay: 1 },
  { cx: 50, cy: 38, r: 2.5, delay: 0 },
  { cx: 65, cy: 32, r: 1.5, delay: 2 },
  { cx: 80, cy: 42, r: 2, delay: 1.5 },
  { cx: 92, cy: 35, r: 1.8, delay: 0.5 },
  { cx: 8, cy: 60, r: 1.5, delay: 1.5 },
  { cx: 22, cy: 55, r: 2, delay: 3 },
  { cx: 45, cy: 58, r: 1.8, delay: 0.5 },
  { cx: 60, cy: 52, r: 2.5, delay: 2.5 },
  { cx: 75, cy: 60, r: 1.5, delay: 1 },
  { cx: 90, cy: 55, r: 2, delay: 0 },
  { cx: 18, cy: 78, r: 2, delay: 2 },
  { cx: 35, cy: 72, r: 1.5, delay: 0 },
  { cx: 55, cy: 80, r: 2.5, delay: 1 },
  { cx: 72, cy: 75, r: 1.8, delay: 3 },
  { cx: 88, cy: 82, r: 2, delay: 0.5 },
  { cx: 5, cy: 90, r: 1.5, delay: 2.5 },
  { cx: 42, cy: 92, r: 2, delay: 1.5 },
  { cx: 78, cy: 88, r: 1.8, delay: 0 },
  { cx: 95, cy: 95, r: 1.5, delay: 2 },
];

// Connect nearby nodes (threshold ~30% distance)
const EDGES: [number, number][] = [];
for (let i = 0; i < NODES.length; i++) {
  for (let j = i + 1; j < NODES.length; j++) {
    const dx = NODES[i].cx - NODES[j].cx;
    const dy = NODES[i].cy - NODES[j].cy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 28) {
      EDGES.push([i, j]);
    }
  }
}

export function ConstellationBackground() {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    // Check prefers-reduced-motion
    const prefersReducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)'
    ).matches;

    if (prefersReducedMotion || !svgRef.current) return;

    const circles = svgRef.current.querySelectorAll('circle');
    circles.forEach((circle, i) => {
      const node = NODES[i];
      if (!node) return;
      circle.style.animation = `constellation-pulse ${3 + node.delay}s ease-in-out ${node.delay}s infinite`;
    });
  }, []);

  return (
    <svg
      ref={svgRef}
      className="absolute inset-0 w-full h-full"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <radialGradient id="constellation-glow" cx="50%" cy="30%" r="60%">
          <stop offset="0%" stopColor="var(--color-primary)" stopOpacity="0.08" />
          <stop offset="100%" stopColor="var(--color-primary)" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Subtle background glow */}
      <rect width="100" height="100" fill="url(#constellation-glow)" />

      {/* Edges */}
      {EDGES.map(([i, j], idx) => (
        <line
          key={`e-${idx}`}
          x1={NODES[i].cx}
          y1={NODES[i].cy}
          x2={NODES[j].cx}
          y2={NODES[j].cy}
          stroke="var(--color-primary)"
          strokeWidth="0.15"
          strokeOpacity="0.12"
        />
      ))}

      {/* Nodes */}
      {NODES.map((node, i) => (
        <circle
          key={`n-${i}`}
          cx={node.cx}
          cy={node.cy}
          r={node.r * 0.4}
          fill="var(--color-primary)"
          opacity={0.25}
        />
      ))}
    </svg>
  );
}
