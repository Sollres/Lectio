import { useState } from "react";
import { ocrDocument, ocrZone, pageImageUrl, uploadPdf } from "./api.js";
import PdfViewer from "./PdfViewer.jsx";
import UploadZone from "./UploadZone.jsx";

export default function App() {
  const [doc, setDoc] = useState(null);          // { id, name, pages: [{width, height}] }
  const [page, setPage] = useState(1);
  const [selections, setSelections] = useState({}); // une zone par page
  const [text, setText] = useState("");
  const [source, setSource] = useState("");
  const [validated, setValidated] = useState([]);  // { id, source, text, zone|null }
  const [resultZone, setResultZone] = useState(null); // zone d'où vient le texte affiché
  const [resultLines, setResultLines] = useState([]);  // lignes détectées du résultat affiché
  const [hoverId, setHoverId] = useState(null);       // résultat survolé dans la liste
  const [busy, setBusy] = useState(null);        // null | "upload" | "doc" | "zone"
  const [error, setError] = useState(null);

  const selection = selections[page] ?? null;
  const pageInfo = doc?.pages[page - 1];
  // éléments validés (vert) et éléments détectés en attente de validation (bleu), page courante
  const highlights = validated
    .map((v, i) => ({ id: v.id, n: i + 1, boxes: v.lines.filter((l) => l.page === page) }))
    .filter((h) => h.boxes.length > 0);
  const preview = resultLines.filter((l) => l.page === page);

  const guard = async (kind, fn) => {
    setBusy(kind);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setBusy(null);
    }
  };

  const loadFile = (file) => {
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Le fichier doit être un PDF.");
      return;
    }
    guard("upload", async () => {
      const d = await uploadPdf(file);
      setDoc(d);
      setPage(1);
      setSelections({});
      setText("");
      setSource("");
      setValidated([]);
      setResultZone(null);
      setResultLines([]);
    });
  };

  const applyResult = (r, zone) => {
    setText(r.text);
    setSource(r.source);
    setResultZone(zone);
    setResultLines(r.lines ?? []);
  };

  const ocrAll = () => guard("doc", async () => applyResult(await ocrDocument(doc.id), null));
  const ocrSelection = () => {
    const zone = { page, rect: selection };
    guard("zone", async () =>
      applyResult(await ocrZone(doc.id, zone.page, zone.rect), zone)
    );
  };

  const setSelection = (rect) => setSelections((s) => ({ ...s, [page]: rect }));

  const validate = () => {
    if (!text.trim()) return;
    const id = `${Date.now()}-${Math.random()}`;
    // éléments à surligner : lignes détectées, ou à défaut le rectangle tracé
    const lines = resultLines.length
      ? resultLines
      : resultZone
        ? [{ page: resultZone.page, text, ...resultZone.rect }]
        : [];
    setValidated((v) => [...v, { id, source, text, lines }]);
    if (resultZone) {
      // le cadre rouge disparaît (sauf si l'utilisateur a tracé autre chose entre-temps)
      setSelections((s) =>
        s[resultZone.page] === resultZone.rect ? { ...s, [resultZone.page]: null } : s
      );
    }
    // prêt pour la suite : le texte est dans la liste des résultats validés
    setText("");
    setSource("");
    setResultZone(null);
    setResultLines([]);
  };

  const download = () => {
    const content = validated.map((v) => `[${v.source}]\n${v.text}`).join("\n\n");
    const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "ocr_valide.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="app">
      <header className="topbar">
        <h1>📖 Lectio</h1>
        {doc && (
          <>
            <span className="muted file-name">{doc.name}</span>
            <button className="btn" onClick={() => setDoc(null)}>
              Changer de PDF
            </button>
          </>
        )}
      </header>

      {error && (
        <div className="error" role="alert">
          <span>{error}</span>
          <button onClick={() => setError(null)} aria-label="Fermer">×</button>
        </div>
      )}

      {!doc ? (
        <UploadZone onFile={loadFile} busy={busy === "upload"} />
      ) : (
        <main className="workspace">
          <section className="viewer">
            <div className="pager">
              <button className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                ◀
              </button>
              <span>
                Page{" "}
                <input
                  type="number"
                  min={1}
                  max={doc.pages.length}
                  value={page}
                  onChange={(e) => {
                    const n = Number(e.target.value);
                    if (n >= 1 && n <= doc.pages.length) setPage(n);
                  }}
                />{" "}
                / {doc.pages.length}
              </span>
              <button
                className="btn"
                disabled={page >= doc.pages.length}
                onClick={() => setPage(page + 1)}
              >
                ▶
              </button>
              <span className="muted small hint">
                Glissez la souris pour tracer une zone. Un simple clic l'efface.
              </span>
            </div>

            <PdfViewer
              key={`${doc.id}-${page}`}
              src={pageImageUrl(doc.id, page)}
              width={pageInfo.width}
              height={pageInfo.height}
              selection={selection}
              onSelect={setSelection}
              highlights={highlights}
              preview={preview}
              activeId={hoverId}
            />
          </section>

          <aside className="panel">
            <h2>Menu</h2>
            <button className="btn primary block" onClick={ocrAll} disabled={!!busy}>
              {busy === "doc" ? "OCR en cours…" : "OCR total"}
            </button>
            <button
              className="btn block"
              onClick={ocrSelection}
              disabled={!selection || !!busy}
              title={selection ? "" : "Tracez d'abord une zone sur le PDF"}
            >
              {busy === "zone" ? "OCR en cours…" : "OCR de la zone sélectionnée"}
            </button>

            <hr />

            <h2>Résultat</h2>
            {source && <p className="muted small">{source}</p>}
            {resultLines.length > 0 && (
              <p className="muted small">
                {resultLines.length} élément(s) détecté(s), encadrés en bleu sur le PDF.
              </p>
            )}
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Le texte reconnu apparaîtra ici (modifiable)…"
              rows={12}
            />
            <button className="btn success block" onClick={validate} disabled={!text.trim()}>
              ✅ Valider
            </button>

            {validated.length > 0 && (
              <details className="validated">
                <summary>Résultats validés ({validated.length})</summary>
                {validated.map((v, i) => (
                  <div
                    key={v.id}
                    className="validated-item"
                    onMouseEnter={() => setHoverId(v.id)}
                    onMouseLeave={() => setHoverId(null)}
                  >
                    <div className="validated-head">
                      <strong>
                        {v.lines.length ? `${i + 1}. ` : ""}
                        {v.source}
                      </strong>
                      <span className="actions">
                        {v.lines.length > 0 && (
                          <button
                            className="link neutral"
                            onClick={() => setPage(v.lines[0].page)}
                          >
                            Voir
                          </button>
                        )}
                        <button
                          className="link"
                          onClick={() => setValidated((list) => list.filter((x) => x.id !== v.id))}
                        >
                          Retirer
                        </button>
                      </span>
                    </div>
                    <pre>{v.text}</pre>
                  </div>
                ))}
                <button className="btn block" onClick={download}>
                  Télécharger (.txt)
                </button>
              </details>
            )}
          </aside>
        </main>
      )}
    </div>
  );
}
