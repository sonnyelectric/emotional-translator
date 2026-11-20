import type { ReplayManifest } from '../protocol/events';
import type { ReplayPhase } from '../replay/clock';
import { provenanceLabel } from '../replay/provenance';

/** Always-visible label that this view is a saved replay, with its provenance (PROTOCOL Replay HTTP). */
export function ReplayBanner(props: {
  manifest: ReplayManifest | null;
  fixtureId: string | null;
  sourceLabel: string;
  staticBuild: boolean;
  phase: ReplayPhase | 'replay_loading';
}) {
  const entry = props.manifest?.fixtures.find((f) => f.id === props.fixtureId) ?? null;
  return (
    <div className="replay-banner" role="note" data-testid="replay-banner">
      <strong className="replay-tag">REPLAY</strong>
      <span>Replay, not live audio.</span>
      {entry && (
        <span className="replay-prov" data-testid="replay-provenance">
          {provenanceLabel(entry)} · <em>{entry.case_name}</em> ({entry.id})
        </span>
      )}
      <span className="replay-src">
        Source: {props.sourceLabel}
        {props.staticBuild ? ' · static demo build, no microphone or backend' : ''}
      </span>
    </div>
  );
}
