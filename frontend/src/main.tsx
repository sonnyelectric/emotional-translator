import { StrictMode, Suspense, lazy } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './app/App';
import './styles/tokens.css';
import './styles/app.css';
import './styles/controls.css';

// ?tune=1   Tuning mode: model-only scores from your mic, no transcript (dev route, live backend).
// ?gallery=1 Visual gallery with hard-coded sample props (no backend, dev builds only).
const params = new URLSearchParams(window.location.search);
const TunePage = lazy(() => import('./tune/TunePage'));
const Gallery = lazy(() => import('./visual/Gallery'));

function Root() {
  if (!__STATIC_REPLAY__ && params.get('tune') === '1') {
    return (
      <Suspense fallback={null}>
        <TunePage />
      </Suspense>
    );
  }
  if (import.meta.env.DEV && params.get('gallery') === '1') {
    return (
      <Suspense fallback={null}>
        <Gallery />
      </Suspense>
    );
  }
  return <App />;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
