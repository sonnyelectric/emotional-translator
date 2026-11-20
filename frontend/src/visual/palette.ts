import type { PaletteName, ScoreLabel, Valence, VisibleCategory } from './contract';

/** TDD 7.2 default palette. */
export const DEFAULT_COLORS: Record<VisibleCategory, string> = {
  angry: '#DC4545',
  disgusted: '#68A876',
  fearful: '#9975D8',
  happy: '#EDB94B',
  sad: '#478CD4',
  surprised: '#EF9858',
};

/** Okabe-Ito colour-vision-deficiency-safe palette (R5 section 5). Shape still carries meaning. */
export const CVD_COLORS: Record<VisibleCategory, string> = {
  angry: '#D55E00',
  disgusted: '#009E73',
  fearful: '#CC79A7',
  happy: '#F0E442',
  sad: '#56B4E9',
  surprised: '#E69F00',
};

export function colorFor(category: VisibleCategory, palette: PaletteName): string {
  return (palette === 'cvd' ? CVD_COLORS : DEFAULT_COLORS)[category];
}

export const LABEL_TEXT: Record<ScoreLabel, string> = {
  angry: 'Angry',
  disgusted: 'Disgusted',
  fearful: 'Fearful',
  happy: 'Happy',
  neutral: 'Neutral',
  other: 'Other',
  sad: 'Sad',
  surprised: 'Surprised',
  unknown: 'Unknown',
};

/** Tiny glyph per category so labels do not rely on colour alone. */
export const GLYPH: Record<VisibleCategory, string> = {
  angry: '▲', // triangle: spikes
  disgusted: '∿', // sine wave
  fearful: '∴', // therefore: tremble
  happy: '●', // filled circle
  sad: '◗', // half circle: droop
  surprised: '✶', // star burst
};

/** Valence used only by the words-versus-voice check. */
export const VOICE_VALENCE: Record<VisibleCategory, Valence> = {
  happy: 'positive',
  surprised: 'positive',
  angry: 'negative',
  sad: 'negative',
  fearful: 'negative',
  disgusted: 'negative',
};

export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

export function rgbToCss(rgb: [number, number, number]): string {
  return `rgb(${Math.round(rgb[0])},${Math.round(rgb[1])},${Math.round(rgb[2])})`;
}
