import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { InboundEvent, ReplayManifest } from '../protocol/events';
import { applyEvent, expectResetAck, initialState, resetLocal, unbindTransport, type TranscriptState } from '../state/reducer';
import {
  selectAnnotation,
  selectAnnotations,
  selectAnnotationsForSegments,
  selectCenterAndHistory,
  selectLatestScores,
} from '../state/selectors';
import { ReplayPlayer, type ReplayPhase } from '../replay/clock';
import {
  ReplayError,
  backendReplaySource,
  bundledReplaySource,
  loadReplay,
  type LoadedReplay,
  type ReplaySource,
} from '../protocol/replayClient';
import { STATIC_REPLAY, backendOrigin, diagnosticsEnabled } from './config';
import type { LivePhase, LiveSession, LocalIssue } from './liveSession';
import {
  DEFAULT_VISUAL_SETTINGS,
  EmotionProfile,
  PhraseInspector,
  SettingsPanel,
  TranscriptView,
  phraseTextFor,
  useMismatch,
  type VisualSettings,
} from './visualBridge';
import { SessionControls, type ControlState } from '../components/SessionControls';
import { Notices } from '../components/Notices';
import { TranscriptHistory } from '../components/TranscriptHistory';
import { ReplayBanner } from '../components/ReplayBanner';
import { StatusPill, describeStatus } from '../components/StatusPill';

export type Mode = 'live' | 'replay';
type ReplayUiPhase = ReplayPhase | 'replay_loading';

const SETTINGS_KEY = 'emotional-translator.settings.v1';

function loadSettings(): VisualSettings {
  let reduced = false;
  try {
    reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    /* ignore */
  }
  const base = { ...DEFAULT_VISUAL_SETTINGS, reducedMotion: reduced };
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY);
    if (!raw) return base;
    const v = JSON.parse(raw) as Partial<VisualSettings>;
    return {
      showLabels: typeof v.showLabels === 'boolean' ? v.showLabels : base.showLabels,
      palette: v.palette === 'cvd' ? 'cvd' : 'default',
      reducedMotion: typeof v.reducedMotion === 'boolean' ? v.reducedMotion || reduced : base.reducedMotion,
      mismatch: typeof v.mismatch === 'boolean' ? v.mismatch : base.mismatch,
    };
  } catch {
    return base;
  }
}

function saveSettings(s: VisualSettings) {
  try {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  } catch {
    /* storage unavailable: settings last for this page only */
  }
}

function devLog(msg: string) {
  if (import.meta.env.DEV) console.debug(`[et] ${msg}`);
}

export function App() {
  // ---------- shared reducer state (live and replay feed the same reducer) ----------
  const stateRef = useRef<TranscriptState>(initialState);
  const [state, setState] = useState<TranscriptState>(initialState);
  const commit = useCallback((next: TranscriptState) => {
    stateRef.current = next;
    setState(next);
  }, []);
  const dispatchEvent = useCallback(
    (e: InboundEvent) => {
      const r = applyEvent(stateRef.current, e);
      if (r.outcome.kind === 'rejected') devLog(`rejected ${e.type}#${e.seq}: ${r.outcome.reason}`);
      else if (r.outcome.kind === 'ignored') devLog(`ignored ${e.type}#${e.seq}: ${r.outcome.reason}`);
      if (r.state !== stateRef.current) commit(r.state);
    },
    [commit],
  );

  const [mode, setMode] = useState<Mode>(STATIC_REPLAY ? 'replay' : 'live');
  const [settings, setSettingsState] = useState<VisualSettings>(loadSettings);
  const setSettings = useCallback((s: VisualSettings) => {
    setSettingsState(s);
    saveSettings(s);
  }, []);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [inspectId, setInspectId] = useState<string | null>(null);

  // ---------- replay ----------
  const origin = useMemo(() => backendOrigin(), []);
  const [useBundled, setUseBundled] = useState<boolean>(STATIC_REPLAY);
  const source: ReplaySource = useMemo(
    () => (useBundled ? bundledReplaySource() : backendReplaySource(origin)),
    [useBundled, origin],
  );
  const [manifest, setManifest] = useState<ReplayManifest | null>(null);
  const [fixtureId, setFixtureId] = useState<string | null>(null);
  const [replayPhase, setReplayPhase] = useState<ReplayUiPhase>('replay_idle');
  const [replayError, setReplayError] = useState<ReplayError | null>(null);
  const [loaded, setLoaded] = useState<LoadedReplay | null>(null);
  const playerRef = useRef<ReplayPlayer<InboundEvent> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const replayGen = useRef(0);

  useEffect(() => {
    if (mode !== 'replay') return;
    const ac = new AbortController();
    setReplayError(null);
    source
      .getManifest(ac.signal)
      .then((m) => {
        setManifest(m);
        setFixtureId((cur) => (cur && m.fixtures.some((f) => f.id === cur) ? cur : m.default_fixture));
      })
      .catch((err: unknown) => {
        if ((err as Error).name === 'AbortError') return;
        setManifest(null);
        setReplayError(err instanceof ReplayError ? err : new ReplayError('Could not load the replay catalog.'));
      });
    return () => ac.abort();
  }, [mode, source]);

  const cancelReplay = useCallback(() => {
    replayGen.current++;
    abortRef.current?.abort();
    abortRef.current = null;
    playerRef.current?.dispose();
    playerRef.current = null;
  }, []);

  const replayStart = useCallback(async () => {
    if (!manifest || !fixtureId) return;
    const entry = manifest.fixtures.find((f) => f.id === fixtureId);
    if (!entry) return;
    cancelReplay();
    const gen = ++replayGen.current;
    const ac = new AbortController();
    abortRef.current = ac;
    setReplayError(null);
    setReplayPhase('replay_loading');
    let data: LoadedReplay;
    try {
      data = await loadReplay(source, entry, ac.signal);
    } catch (err) {
      if (gen !== replayGen.current || (err as Error).name === 'AbortError') return;
      setReplayPhase('replay_idle');
      setReplayError(err instanceof ReplayError ? err : new ReplayError('The saved fixture could not be loaded.'));
      return;
    }
    if (gen !== replayGen.current) return;
    data.diagnostics.forEach(devLog);
    setLoaded(data);
    commit(unbindTransport(resetLocal()));
    const player = new ReplayPlayer<InboundEvent>(
      data.events,
      (e) => {
        if (gen === replayGen.current) dispatchEvent(e);
      },
      (p) => {
        if (gen === replayGen.current) setReplayPhase(p);
      },
    );
    playerRef.current = player;
    player.play();
  }, [manifest, fixtureId, source, cancelReplay, commit, dispatchEvent]);

  // ---------- live ----------
  const liveRef = useRef<LiveSession | null>(null);
  const [livePhase, setLivePhase] = useState<LivePhase>('idle');
  const [localIssue, setLocalIssue] = useState<LocalIssue | null>(null);

  const getLive = useCallback(async (): Promise<LiveSession | null> => {
    if (__STATIC_REPLAY__) return null;
    if (liveRef.current) return liveRef.current;
    const { LiveSession: Ctor } = await import('./liveSession');
    liveRef.current = new Ctor(
      origin,
      {
        onEvent: dispatchEvent,
        onPhase: setLivePhase,
        onLocalIssue: setLocalIssue,
        onDiagnostic: devLog,
      },
      diagnosticsEnabled(),
    );
    return liveRef.current;
  }, [origin, dispatchEvent]);

  useEffect(() => {
    if (mode === 'live') liveRef.current?.syncStatus(state.status);
  }, [mode, state.status]);

  useEffect(
    () => () => {
      cancelReplay();
      void liveRef.current?.dispose();
    },
    [cancelReplay],
  );

  useEffect(() => {
    if (!inspectId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setInspectId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [inspectId]);

  // ---------- derived ----------
  const status = state.status;
  const hasContent = state.segments.length > 0 || state.partial !== null || Object.keys(state.annotations).length > 0;
  const serverState = status?.mode === 'live' ? status.state : null;
  const recording =
    livePhase === 'permission' ||
    livePhase === 'connecting' ||
    (livePhase === 'active' && (serverState === 'connecting' || serverState === 'listening' || serverState === 'paused' || serverState === 'stopping'));

  const controls: ControlState = useMemo(() => {
    if (mode === 'replay') {
      const idle = replayPhase === 'replay_idle';
      return {
        start: idle && !hasContent && !!manifest && !!fixtureId,
        pause: replayPhase === 'replay_playing',
        resume: replayPhase === 'replay_paused',
        stop: replayPhase === 'replay_playing' || replayPhase === 'replay_paused' || replayPhase === 'replay_loading',
        reset: replayPhase !== 'replay_playing' && replayPhase !== 'replay_loading' && (hasContent || replayPhase === 'replay_done' || !!replayError),
        modeSwitch: !STATIC_REPLAY && idle && !hasContent,
        paused: replayPhase === 'replay_paused',
      };
    }
    const reusable = livePhase === 'active' && serverState === 'idle' && !hasContent;
    return {
      start: (livePhase === 'idle' && !hasContent && state.sessionId === null) || reusable,
      pause: livePhase === 'active' && serverState === 'listening',
      resume: livePhase === 'active' && serverState === 'paused',
      stop: livePhase === 'permission' || livePhase === 'connecting' || (livePhase === 'active' && (serverState === 'connecting' || serverState === 'listening' || serverState === 'paused')),
      reset: !recording && (hasContent || livePhase === 'closed' || state.sessionId !== null || !!state.error),
      modeSwitch: !recording && livePhase !== 'closed' && !hasContent && state.sessionId === null,
      paused: serverState === 'paused',
    };
  }, [mode, replayPhase, hasContent, manifest, fixtureId, replayError, livePhase, serverState, state.sessionId, state.error, recording]);

  const onStart = useCallback(async () => {
    if (mode === 'replay') return replayStart();
    const live = await getLive();
    if (!live) return;
    if (live.currentPhase === 'active' && live.transportOpen) live.startOnOpenTransport();
    else {
      commit(unbindTransport(stateRef.current));
      await live.start();
    }
  }, [mode, replayStart, getLive, commit]);

  const onPause = useCallback(() => {
    if (mode === 'replay') playerRef.current?.pause();
    else void liveRef.current?.pause();
  }, [mode]);

  const onResume = useCallback(() => {
    if (mode === 'replay') playerRef.current?.resume();
    else void liveRef.current?.resume();
  }, [mode]);

  const onStop = useCallback(() => {
    if (mode === 'replay') {
      if (replayPhase === 'replay_loading') {
        cancelReplay();
        setReplayPhase('replay_idle');
      } else playerRef.current?.stop();
    } else void liveRef.current?.stop();
  }, [mode, replayPhase, cancelReplay]);

  const onReset = useCallback(() => {
    setInspectId(null);
    if (mode === 'replay') {
      cancelReplay();
      setReplayPhase('replay_idle');
      setLoaded(null);
      setReplayError(null);
      commit(resetLocal());
      return;
    }
    const live = liveRef.current;
    setLocalIssue(null);
    if (live && live.transportOpen) {
      commit(expectResetAck(stateRef.current));
      if (live.reset()) return; // server acknowledges with session.reset under a new ID
    } else {
      live?.reset();
    }
    commit(resetLocal());
  }, [mode, cancelReplay, commit]);

  /** Switch modes after clearing local state. Callers check the lock (no active recording). */
  const switchMode = useCallback(
    (m: Mode) => {
      if (m === mode) return;
      cancelReplay();
      void liveRef.current?.dispose();
      setLivePhase('idle');
      setLocalIssue(null);
      setReplayPhase('replay_idle');
      setReplayError(null);
      setLoaded(null);
      commit(resetLocal());
      setMode(m);
    },
    [mode, cancelReplay, commit],
  );
  const onModeChange = useCallback(
    (m: Mode) => {
      if (controls.modeSwitch) switchMode(m);
    },
    [controls.modeSwitch, switchMode],
  );

  // ---------- view data ----------
  const allAnnotations = useMemo(() => selectAnnotations(state), [state]);
  const { center, history } = useMemo(() => selectCenterAndHistory(state.segments, 3), [state.segments]);
  const centerAnnotations = useMemo(() => selectAnnotationsForSegments(allAnnotations, center), [allAnnotations, center]);
  const historyAnnotations = useMemo(() => selectAnnotationsForSegments(allAnnotations, history), [allAnnotations, history]);
  const latestScores = useMemo(() => selectLatestScores(state), [state]);
  const inspected = useMemo(() => selectAnnotation(state, inspectId), [state, inspectId]);
  const { results: mismatch, status: mismatchStatus } = useMismatch(state.segments, allAnnotations, settings.mismatch);
  const effectiveMismatch = settings.mismatch ? mismatch : undefined;
  const inspectedText = useMemo(() => phraseTextFor(inspected, state.segments), [inspected, state.segments]);
  const partial = state.partial ? { partial_id: state.partial.partial_id, text: state.partial.text } : null;
  const lastCommitted = state.segments.length > 0 ? state.segments[state.segments.length - 1] : null;

  const statusInfo = describeStatus({ mode, livePhase, status, replayPhase, error: state.error, localIssue });
  const showIdlePrompt = !hasContent && (mode === 'live' ? !recording : replayPhase === 'replay_idle' || replayPhase === 'replay_loading');

  return (
    <div className="app" data-mode={mode} data-reduced-motion={settings.reducedMotion ? 'true' : 'false'}>
      {mode === 'replay' && (
        <ReplayBanner
          manifest={manifest}
          fixtureId={loaded?.entry.id ?? fixtureId}
          sourceLabel={source.label}
          staticBuild={STATIC_REPLAY}
          phase={replayPhase}
        />
      )}
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22">
              <path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </span>
          <h1>Emotional Translator</h1>
          <span className="tagline">Captions that show how something was said</span>
        </div>
        <div className="header-right">
          <span className={`mode-badge mode-${mode}`} data-testid="mode-badge">
            {mode === 'live' ? 'LIVE' : 'REPLAY'}
          </span>
          <StatusPill info={statusInfo} />
          <button
            type="button"
            className="icon-btn"
            aria-expanded={settingsOpen}
            aria-controls="settings-drawer"
            onClick={() => setSettingsOpen((o) => !o)}
          >
            Settings
          </button>
        </div>
        {settingsOpen && (
          <div id="settings-drawer" className="settings-drawer">
            <SettingsPanel settings={settings} onChange={setSettings} mismatchAvailable={mismatchStatus !== 'unavailable'} />
            {settings.mismatch && mismatchStatus === 'loading' ? (
              <p className="settings-note">Words-vs-voice text model is warming up (first use downloads about 68 MB).</p>
            ) : null}
            {mismatchStatus === 'unavailable' ? (
              <p className="settings-note">Words-vs-voice check is off: the text model could not load.</p>
            ) : null}
          </div>
        )}
      </header>

      <Notices
        mode={mode}
        notices={state.notices}
        error={state.error}
        localIssue={localIssue}
        status={status}
        replayError={replayError}
        canUseBundled={mode === 'replay' && !useBundled}
        onUseBundled={() => setUseBundled(true)}
        onSwitchToReplay={!STATIC_REPLAY && mode === 'live' && !recording ? () => switchMode('replay') : undefined}
      />

      <main className="layout">
        <aside className="profile-panel" aria-label="Emotion profile">
          <EmotionProfile latest={latestScores} settings={settings} />
          <p className="panel-note">
            Detected vocal cues from the emotion2vec+ model, not a reading of anyone&apos;s feelings.
          </p>
        </aside>

        <section className="panel transcript-panel" aria-labelledby="transcript-title">
          <div className="panel-head">
            <h2 id="transcript-title">{mode === 'live' ? 'Live transcript' : 'Saved replay transcript'}</h2>
          </div>
          <div className="center-stage" data-testid="center-transcript">
            {showIdlePrompt ? (
              <div className="idle-prompt">
                <svg className="idle-mic" viewBox="0 0 24 24" width="40" height="40" aria-hidden="true">
                  <rect x="9" y="3" width="6" height="11" rx="3" fill="none" stroke="currentColor" strokeWidth="1.6" />
                  <path d="M6 11a6 6 0 0 0 12 0M12 17v4M9 21h6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
                <p>
                  {mode === 'live'
                    ? 'Start listening to see vocal emotion cues.'
                    : 'Press Start to play a saved result. Nothing here is live.'}
                </p>
              </div>
            ) : (
              <TranscriptView
                segments={center}
                partial={partial}
                annotations={centerAnnotations}
                settings={settings}
                onInspect={setInspectId}
                mismatch={effectiveMismatch}
                selectedAnnotationId={inspectId}
              />
            )}
          </div>
          <div className="sr-only" aria-live="polite">
            {lastCommitted ? lastCommitted.text : ''}
          </div>
        </section>

        <TranscriptHistory
          segments={history}
          annotations={historyAnnotations}
          settings={settings}
          onInspect={setInspectId}
          mismatch={effectiveMismatch}
        />
      </main>

      <SessionControls
        mode={mode}
        controls={controls}
        onStart={() => void onStart()}
        onPause={onPause}
        onResume={onResume}
        onStop={onStop}
        onReset={onReset}
        onModeChange={onModeChange}
        staticReplay={STATIC_REPLAY}
        fixtures={mode === 'replay' ? manifest?.fixtures ?? [] : []}
        fixtureId={fixtureId}
        onFixtureChange={setFixtureId}
      />

      {inspected && (
        <div className="inspector-wrap">
          <PhraseInspector
            annotation={inspected}
            onClose={() => setInspectId(null)}
            phraseText={inspectedText}
            mismatch={effectiveMismatch?.get(inspected.segment_id) ?? null}
            palette={settings.palette}
          />
        </div>
      )}
    </div>
  );
}
