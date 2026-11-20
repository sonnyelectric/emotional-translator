// The ONE place the shell imports Builder BC2's visual components (PLAN section 5).
//
// Integrator: to switch to BC2's real components, replace the block below with e.g.
//   export { TranscriptView } from '../visual/TranscriptView';
//   export { EmotionProfile } from '../visual/EmotionProfile';
//   export { PhraseInspector } from '../visual/PhraseInspector';
//   export { SettingsPanel } from '../visual/SettingsPanel';
//   export { useMismatch } from '../mismatch/useMismatch';
//   export type { VisualSettings, ... } from '../visual/contract';
// then run `npm run typecheck`; any prop drift shows up in App.tsx / adapters below.
export {
  TranscriptView,
  EmotionProfile,
  PhraseInspector,
  SettingsPanel,
  useMismatch,
} from '../visual/_placeholder';
export type {
  VisualSettings,
  SegmentView,
  PartialView,
  AnnotationView,
  MismatchResult,
} from '../visual/_placeholder';

import type { VisualSettings } from '../visual/_placeholder';

export const DEFAULT_VISUAL_SETTINGS: VisualSettings = {
  showLabels: false,
  palette: 'default',
  reducedMotion: false,
  mismatch: true,
};
