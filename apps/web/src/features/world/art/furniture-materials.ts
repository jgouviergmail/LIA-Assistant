import type { Tone } from '../types';

/** Material roles keep an owner's accent without tinting every surface alike. */
export const FURNITURE: Record<Tone, { frame: string; top: string; fabric: string; trim: string }> =
  {
    sage: { frame: '#334d42', top: '#d9d0b2', fabric: '#3f785b', trim: '#c8ac70' },
    teal: { frame: '#293e50', top: '#e2ddcd', fabric: '#278f91', trim: '#d2aa64' },
    clay: { frame: '#593b35', top: '#e6d2b1', fabric: '#c94d43', trim: '#e4b770' },
    violet: { frame: '#3c334c', top: '#ded1b6', fabric: '#67508e', trim: '#d7af62' },
    amber: { frame: '#3e3933', top: '#76533d', fabric: '#b8813b', trim: '#d5b575' },
    cream: { frame: '#344b55', top: '#e8dfc9', fabric: '#dfcfa9', trim: '#94744e' },
  };
