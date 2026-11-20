import { useEffect, useRef } from 'react';
import { CloudEngine, type CloudSpec } from './cloudEngine';

/** Pointer-transparent SVG layer that sits behind the text and hosts the cloud engine. */
export function CloudLayer({ specs, reducedMotion }: { specs: CloudSpec[]; reducedMotion: boolean }) {
  const ref = useRef<SVGSVGElement>(null);
  const engine = useRef<CloudEngine | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const e = new CloudEngine(ref.current);
    engine.current = e;
    return () => {
      e.destroy();
      engine.current = null;
    };
  }, []);

  useEffect(() => {
    engine.current?.setReducedMotion(reducedMotion);
  }, [reducedMotion]);

  useEffect(() => {
    engine.current?.sync(specs);
  }, [specs]);

  return <svg ref={ref} className="et-cloud-layer" aria-hidden="true" focusable="false" />;
}
