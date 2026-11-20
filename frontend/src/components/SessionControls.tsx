import type { ReplayFixtureEntry } from '../protocol/events';
import type { Mode } from '../app/App';

export interface ControlState {
  start: boolean;
  pause: boolean;
  resume: boolean;
  stop: boolean;
  reset: boolean;
  modeSwitch: boolean;
  paused: boolean;
}

interface Props {
  mode: Mode;
  controls: ControlState;
  onStart(): void;
  onPause(): void;
  onResume(): void;
  onStop(): void;
  onReset(): void;
  onModeChange(m: Mode): void;
  staticReplay: boolean;
  fixtures: readonly ReplayFixtureEntry[];
  fixtureId: string | null;
  onFixtureChange(id: string): void;
}

export function SessionControls(p: Props) {
  const { controls: c } = p;
  return (
    <footer className="controls" aria-label="Session controls">
      <div className="controls-group">
        {!p.staticReplay && (
          <div className="segmented" role="radiogroup" aria-label="Mode">
            {(['live', 'replay'] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={p.mode === m}
                className={p.mode === m ? 'seg-btn active' : 'seg-btn'}
                disabled={!c.modeSwitch && p.mode !== m}
                title={!c.modeSwitch ? 'Stop and Reset before switching mode' : undefined}
                onClick={() => p.onModeChange(m)}
              >
                {m === 'live' ? 'Live' : 'Replay'}
              </button>
            ))}
          </div>
        )}
        {p.mode === 'replay' && p.fixtures.length > 0 && (
          <label className="fixture-pick">
            <span>Saved result</span>
            <select
              value={p.fixtureId ?? ''}
              disabled={!c.start}
              onChange={(e) => p.onFixtureChange(e.target.value)}
              data-testid="fixture-select"
            >
              {p.fixtures.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.case_name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="controls-group buttons">
        <button type="button" className="btn primary" disabled={!c.start} onClick={p.onStart} data-testid="btn-start">
          {p.mode === 'live' ? 'Start listening' : 'Start replay'}
        </button>
        {c.paused ? (
          <button type="button" className="btn" disabled={!c.resume} onClick={p.onResume} data-testid="btn-resume">
            Resume
          </button>
        ) : (
          <button type="button" className="btn" disabled={!c.pause} onClick={p.onPause} data-testid="btn-pause">
            Pause
          </button>
        )}
        <button type="button" className="btn" disabled={!c.stop} onClick={p.onStop} data-testid="btn-stop">
          Stop
        </button>
        <button type="button" className="btn ghost" disabled={!c.reset} onClick={p.onReset} data-testid="btn-reset">
          Reset
        </button>
      </div>
    </footer>
  );
}
