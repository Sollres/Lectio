import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { createMobileSession, getMobileSession } from "./api.js";

/**
 * Fenêtre « Photo depuis le téléphone » : affiche un QR code, puis attend que la photo arrive.
 * `onDocument(doc)` reçoit le document créé à partir de la photo.
 */
export default function MobileCapture({ onDocument, onClose }) {
  const [session, setSession] = useState(null); // { token, url }
  const [qr, setQr] = useState(null);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);    // incrémenté pour générer un nouveau QR code

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    setSession(null);
    setQr(null);
    setError(null);

    (async () => {
      try {
        const s = await createMobileSession();
        if (cancelled) return;
        setSession(s);
        setQr(await QRCode.toDataURL(s.url, { width: 280, margin: 1 }));

        const poll = async () => {
          try {
            const r = await getMobileSession(s.token);
            if (cancelled) return;
            if (r.status === "done") {
              onDocument(r.document);
              return;
            }
          } catch (e) {
            if (cancelled) return;
            if (e.status === 404) {
              setError("Le QR code a expiré. Générez-en un nouveau.");
              return;
            }
            // autre erreur (réseau…) : on réessaie
          }
          timer = setTimeout(poll, 1500);
        };
        poll();
      } catch (e) {
        if (!cancelled) setError(e.message || "Impossible de créer la session.");
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>📱 Photo depuis le téléphone</h2>

        {error ? (
          <>
            <p className="error-text">{error}</p>
            <button className="btn primary block" onClick={() => setAttempt((a) => a + 1)}>
              Nouveau QR code
            </button>
          </>
        ) : qr ? (
          <>
            <img className="qr" src={qr} alt="QR code à scanner" />
            <p>
              Scannez ce QR code avec l'appareil photo de votre téléphone, prenez le document en
              photo, puis envoyez-la.
            </p>
            <p className="muted small">Le téléphone et l'ordinateur doivent être sur le même Wi-Fi.</p>
            <p className="muted small url">{session.url}</p>
            <p className="waiting">⏳ En attente de la photo…</p>
          </>
        ) : (
          <p className="muted">Préparation…</p>
        )}

        <button className="btn block" onClick={onClose}>
          Annuler
        </button>
      </div>
    </div>
  );
}
