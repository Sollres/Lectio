import { useRef, useState } from "react";

const clamp = (v) => Math.min(Math.max(v, 0), 1);

const boxStyle = (b) => ({
  left: `${b.x * 100}%`,
  top: `${b.y * 100}%`,
  width: `${b.w * 100}%`,
  height: `${b.h * 100}%`,
});

const rectOf = (a, b) => ({
  x: Math.min(a.x, b.x),
  y: Math.min(a.y, b.y),
  w: Math.abs(a.x - b.x),
  h: Math.abs(a.y - b.y),
});

/**
 * Affiche une page et permet de tracer une zone à la souris.
 * `selection` / `onSelect` utilisent des coordonnées normalisées (0 à 1).
 * `highlights` : éléments validés, surlignés en vert ({ id, n, boxes: [{x,y,w,h}] }).
 * `preview`    : éléments détectés, pas encore validés, encadrés en bleu.
 */
export default function PdfViewer({
  src,
  width,
  height,
  selection,
  onSelect,
  highlights = [],
  preview = [],
  activeId = null,
}) {
  const overlayRef = useRef(null);
  const startRef = useRef(null);
  const [draft, setDraft] = useState(null);

  const point = (e) => {
    const b = overlayRef.current.getBoundingClientRect();
    return { x: clamp((e.clientX - b.left) / b.width), y: clamp((e.clientY - b.top) / b.height) };
  };

  const onPointerDown = (e) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    startRef.current = point(e);
    setDraft(null);
  };

  const onPointerMove = (e) => {
    if (!startRef.current) return;
    setDraft(rectOf(startRef.current, point(e)));
  };

  const onPointerUp = (e) => {
    if (!startRef.current) return;
    const r = rectOf(startRef.current, point(e));
    const box = overlayRef.current.getBoundingClientRect();
    startRef.current = null;
    setDraft(null);
    // simple clic ou zone minuscule (< 5 px) : on efface la sélection
    onSelect(r.w * box.width < 5 || r.h * box.height < 5 ? null : r);
  };

  const onPointerCancel = () => {
    startRef.current = null;
    setDraft(null);
  };

  const shown = draft || selection;

  return (
    <div className="page" style={{ aspectRatio: `${width} / ${height}` }}>
      <img src={src} alt="Page du PDF" draggable={false} />
      {preview.map((b, j) => (
        <div key={`p${j}`} className="preview" style={boxStyle(b)} />
      ))}
      {highlights.map((h) =>
        h.boxes.map((b, j) => (
          <div
            key={`${h.id}-${j}`}
            className={`highlight ${h.id === activeId ? "active" : ""}`}
            style={boxStyle(b)}
          >
            {j === 0 && <span className="badge">{h.n}</span>}
          </div>
        ))
      )}
      <div
        ref={overlayRef}
        className="overlay"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
      >
        {shown && (
          <div
            className="selection"
            style={{
              left: `${shown.x * 100}%`,
              top: `${shown.y * 100}%`,
              width: `${shown.w * 100}%`,
              height: `${shown.h * 100}%`,
            }}
          />
        )}
      </div>
    </div>
  );
}
