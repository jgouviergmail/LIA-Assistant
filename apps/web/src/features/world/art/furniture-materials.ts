import type { Tone } from '../types';

/** Material roles keep an owner's accent without tinting every surface alike. */
export const FURNITURE: Record<Tone, { frame: string; top: string; fabric: string; trim: string }> =
  {
    sage: { frame: '#3d5146', top: '#e2d7bc', fabric: '#48895a', trim: '#c3a16a' },
    teal: { frame: '#344950', top: '#e9e1ce', fabric: '#278e8b', trim: '#c9a36a' },
    clay: { frame: '#59423b', top: '#e6d4b5', fabric: '#cf6550', trim: '#cca06a' },
    violet: { frame: '#494151', top: '#e6d9c0', fabric: '#8563ab', trim: '#c59d71' },
    amber: { frame: '#49433b', top: '#89623e', fabric: '#c39440', trim: '#ceb078' },
    cream: { frame: '#425558', top: '#f1e8d3', fabric: '#e5d4ae', trim: '#aa8453' },
  };
