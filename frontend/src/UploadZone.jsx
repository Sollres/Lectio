import { useRef, useState } from "react";

export default function UploadZone({ onFile, busy }) {
  const inputRef = useRef(null);
  const [over, setOver] = useState(false);

  return (
    <div
      className={`upload ${over ? "over" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      <p className="upload-title">{busy ? "Chargement du PDF…" : "Déposez un PDF ici"}</p>
      <p className="muted">ou</p>
      <button className="btn primary" disabled={busy} onClick={() => inputRef.current.click()}>
        Charger un PDF
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}
