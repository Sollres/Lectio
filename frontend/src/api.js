async function request(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* réponse sans JSON */
    }
    throw new Error(detail || `Erreur ${res.status}`);
  }
  return res.json();
}

export function uploadPdf(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/documents", { method: "POST", body: form });
}

export const pageImageUrl = (docId, page) => `/api/documents/${docId}/pages/${page}/image`;

export const ocrDocument = (docId) =>
  request(`/api/documents/${docId}/ocr`, { method: "POST" });

// rect : { x, y, w, h } en coordonnées normalisées (0 à 1)
export const ocrZone = (docId, page, rect) =>
  request(`/api/documents/${docId}/ocr/zone`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page, x: rect.x, y: rect.y, w: rect.w, h: rect.h }),
  });
