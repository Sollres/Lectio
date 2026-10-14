"""
Lectio – API (FastAPI + PyMuPDF + PaddleOCR)

Lancement (depuis le dossier backend/) :
    uvicorn main:app --port 8000
"""

import io
import ipaddress
import secrets
import socket
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

ZOOM = 2.0          # 2.0 ≈ 144 dpi : bon compromis qualité / vitesse
OCR_LANG = "fr"
MAX_DOCS = 10       # nombre de PDF gardés en mémoire

# ---------------------------------------------------------------- PaddleOCR
_ocr = None
_ocr_lock = threading.Lock()  # un seul OCR à la fois (Paddle n'aime pas le parallèle)


def _load_ocr():
    from paddleocr import PaddleOCR

    try:  # PaddleOCR 3.x
        return PaddleOCR(
            lang=OCR_LANG,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except (TypeError, ValueError):  # PaddleOCR 2.x
        return PaddleOCR(lang=OCR_LANG, use_angle_cls=True)


def _item(text, poly) -> dict:
    """Texte + rectangle englobant (en pixels) à partir du polygone détecté."""
    pts = np.asarray(poly, dtype=float).reshape(-1, 2)
    return {
        "text": str(text),
        "x0": float(pts[:, 0].min()), "y0": float(pts[:, 1].min()),
        "x1": float(pts[:, 0].max()), "y1": float(pts[:, 1].max()),
    }


def run_ocr(img: Image.Image) -> list[dict]:
    """Lignes de texte détectées : {text, x0, y0, x1, y1}, en pixels de `img`."""
    global _ocr
    arr = np.array(img.convert("RGB"))
    items: list[dict] = []
    with _ocr_lock:
        if _ocr is None:
            _ocr = _load_ocr()
        if hasattr(_ocr, "predict"):  # 3.x
            for r in _ocr.predict(arr):
                texts = list(r["rec_texts"])
                try:
                    polys = r["rec_polys"]
                except (KeyError, TypeError):
                    polys = r["dt_polys"]
                items += [_item(t, p) for t, p in zip(texts, polys)]
        else:  # 2.x
            res = _ocr.ocr(arr)
            for poly, (text, _score) in (res[0] or []):
                items.append(_item(text, poly))
    return items


def to_lines(items, page: int, width: int, height: int, dx: float = 0.0, dy: float = 0.0):
    """Convertit les rectangles en pixels vers des coordonnées normalisées (0 à 1) de la page."""
    clamp = lambda v: min(max(v, 0.0), 1.0)
    out = []
    for it in items:
        x0, x1 = clamp((it["x0"] + dx) / width), clamp((it["x1"] + dx) / width)
        y0, y1 = clamp((it["y0"] + dy) / height), clamp((it["y1"] + dy) / height)
        out.append({"page": page, "text": it["text"], "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})
    return out


def _warmup():
    global _ocr
    with _ocr_lock:
        if _ocr is None:
            _ocr = _load_ocr()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # charge le modèle en arrière-plan pour que le premier OCR soit rapide
    threading.Thread(target=_warmup, daemon=True).start()
    yield


app = FastAPI(title="Lectio", lifespan=lifespan)

# ---------------------------------------------------------------- Sécurité réseau
# L'API écoute sur le réseau local (pour le téléphone) mais, depuis une autre machine,
# seules la page photo et l'envoi de photo sont accessibles. Tout le reste est réservé
# à l'ordinateur lui-même.
LAN_ROUTES = ("/mobile/", "/api/mobile/upload/")


@app.middleware("http")
async def lan_guard(request: Request, call_next):
    host = request.client.host if request.client else ""
    try:
        ip = ipaddress.ip_address(host)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        local = ip.is_loopback
    except ValueError:
        local = host == "localhost"
    if not local and not request.url.path.startswith(LAN_ROUTES):
        return JSONResponse({"detail": "Accès réservé à l'ordinateur local."}, status_code=403)
    return await call_next(request)

# ---------------------------------------------------------------- Documents
docs: "OrderedDict[str, bytes]" = OrderedDict()


def get_pdf(doc_id: str) -> bytes:
    pdf = docs.get(doc_id)
    if pdf is None:
        raise HTTPException(404, "Document introuvable (le serveur a peut-être redémarré). Rechargez le PDF.")
    return pdf


def _render(doc: fitz.Document, index: int) -> Image.Image:
    pix = doc[index].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


@lru_cache(maxsize=12)
def render_page(doc_id: str, page: int) -> Image.Image:
    doc = fitz.open(stream=get_pdf(doc_id), filetype="pdf")
    if not 1 <= page <= len(doc):
        raise HTTPException(404, f"Page {page} inexistante.")
    return _render(doc, page - 1)


# ---------------------------------------------------------------- Routes
class Zone(BaseModel):
    page: int = Field(ge=1)
    x: float = Field(ge=0, le=1)   # coordonnées normalisées (0 à 1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


def register_pdf(data: bytes, name: str) -> dict:
    """Valide un PDF, le garde en mémoire et renvoie sa description."""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        pages = [
            {"width": round(p.rect.width * ZOOM), "height": round(p.rect.height * ZOOM)}
            for p in doc
        ]
    except Exception:
        raise HTTPException(400, "PDF illisible.")
    if not pages:
        raise HTTPException(400, "Le PDF ne contient aucune page.")

    doc_id = uuid.uuid4().hex
    docs[doc_id] = data
    while len(docs) > MAX_DOCS:
        docs.popitem(last=False)
    return {"id": doc_id, "name": name, "pages": pages}


@app.post("/api/documents")
def upload(file: UploadFile = File(...)):
    return register_pdf(file.file.read(), file.filename)


@app.get("/api/documents/{doc_id}/pages/{page}/image")
def page_image(doc_id: str, page: int):
    buf = io.BytesIO()
    render_page(doc_id, page).save(buf, format="JPEG", quality=90)
    return Response(
        buf.getvalue(),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.post("/api/documents/{doc_id}/ocr")
def ocr_document(doc_id: str):
    doc = fitz.open(stream=get_pdf(doc_id), filetype="pdf")
    parts, lines = [], []
    for i in range(len(doc)):
        img = _render(doc, i)
        items = run_ocr(img)
        parts.append(f"--- Page {i + 1} ---\n" + "\n".join(it["text"] for it in items))
        lines += to_lines(items, i + 1, img.width, img.height)
    return {"source": "Document complet", "text": "\n\n".join(parts), "lines": lines}


@app.post("/api/documents/{doc_id}/ocr/zone")
def ocr_zone(doc_id: str, z: Zone):
    img = render_page(doc_id, z.page)
    left, top = int(z.x * img.width), int(z.y * img.height)
    right = min(img.width, int((z.x + z.w) * img.width) + 1)
    bottom = min(img.height, int((z.y + z.h) * img.height) + 1)
    if right - left < 5 or bottom - top < 5:
        raise HTTPException(400, "Zone trop petite.")
    # petite marge blanche : aide la détection du texte collé au bord de la zone
    border = 12
    crop = ImageOps.expand(img.crop((left, top, right, bottom)), border=border, fill="white")
    items = run_ocr(crop)
    # coordonnées du recadrage -> coordonnées de la page entière
    lines = to_lines(items, z.page, img.width, img.height, dx=left - border, dy=top - border)
    return {
        "source": f"Page {z.page} – zone ({left},{top},{right - left}×{bottom - top})",
        "text": "\n".join(it["text"] for it in items),
        "lines": lines,
    }


# ---------------------------------------------------------------- Photo depuis le téléphone
SESSION_TTL = 15 * 60                 # durée de validité d'un QR code (secondes)
MAX_PHOTO_BYTES = 25 * 1024 * 1024
PHOTO_LONG_SIDE_PT = 1100             # taille de la page créée : le grand côté fait ~2200 px une fois rendu
mobile_sessions: dict[str, dict] = {}

MOBILE_HTML = r'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lectio – Photo</title>
<style>
body{margin:0;font-family:system-ui,-apple-system,sans-serif;background:#f4f5f7;color:#1f2430;text-align:center;padding:24px}
h1{font-size:1.4rem;margin:8px 0 4px}
p{color:#6b7280}
.btn{display:block;width:100%;max-width:360px;margin:14px auto 0;padding:16px;border:0;border-radius:12px;font-size:1.1rem;background:#3b5bdb;color:#fff}
.btn.alt{background:#fff;color:#1f2430;border:1px solid #d9dce3}
.btn:disabled{opacity:.5}
img{max-width:100%;max-height:55vh;border-radius:8px;margin-top:16px;box-shadow:0 2px 10px rgba(0,0,0,.15)}
#msg{margin-top:16px;font-weight:600;color:#1f2430}
</style></head><body>
<h1>📖 Lectio</h1>
<p>Prenez votre document en photo, bien à plat et bien éclairé.</p>
<input id="file" type="file" accept="image/*" capture="environment" hidden>
<img id="preview" hidden alt="Aperçu">
<button class="btn" id="take">📷 Prendre une photo</button>
<button class="btn" id="send" hidden>Envoyer vers Lectio</button>
<p id="msg"></p>
<script>
const TOKEN = "__TOKEN__";
const $ = (id) => document.getElementById(id);
let blob = null;

// Réduit la photo (max 2600 px) et la convertit en JPEG : upload plus rapide, HEIC géré
function shrink(file) {
  return new Promise((ok, ko) => {
    const url = URL.createObjectURL(file);
    const im = new Image();
    im.onload = () => {
      const k = Math.min(1, 2600 / Math.max(im.naturalWidth, im.naturalHeight));
      const c = document.createElement("canvas");
      c.width = Math.round(im.naturalWidth * k);
      c.height = Math.round(im.naturalHeight * k);
      c.getContext("2d").drawImage(im, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      c.toBlob((b) => (b ? ok(b) : ko(new Error("conversion"))), "image/jpeg", 0.9);
    };
    im.onerror = () => ko(new Error("image"));
    im.src = url;
  });
}

$("take").onclick = () => $("file").click();

$("file").onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  $("msg").textContent = "Préparation…";
  try { blob = await shrink(f); } catch (err) { blob = f; }
  $("preview").src = URL.createObjectURL(blob);
  $("preview").hidden = false;
  $("send").hidden = false;
  $("send").disabled = false;
  $("take").textContent = "🔄 Reprendre la photo";
  $("take").className = "btn alt";
  $("msg").textContent = "";
  e.target.value = "";
};

$("send").onclick = async () => {
  $("send").disabled = true;
  $("msg").textContent = "Envoi…";
  const fd = new FormData();
  fd.append("file", blob, "photo.jpg");
  try {
    const r = await fetch("/api/mobile/upload/" + TOKEN, { method: "POST", body: fd });
    if (!r.ok) {
      let d = "Erreur d'envoi";
      try { d = (await r.json()).detail || d; } catch (x) {}
      throw new Error(d);
    }
    document.body.innerHTML = `<h1>✅ Photo envoyée</h1><p>Regardez l'écran de votre ordinateur : le document est prêt dans Lectio.</p>`;
  } catch (err) {
    $("msg").textContent = "⚠️ " + err.message;
    $("send").disabled = false;
  }
};
</script></body></html>
'''

EXPIRED_HTML = (
    "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
    "<body style='font-family:system-ui;text-align:center;padding:40px'>"
    "<h2>Lien expiré</h2><p>Générez un nouveau QR code dans Lectio.</p>"
)


def lan_ip() -> str:
    """Adresse de l'ordinateur sur le réseau local (aucun paquet n'est envoyé)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _purge_sessions():
    now = time.time()
    for t in [t for t, s in mobile_sessions.items() if now - s["created"] > SESSION_TTL]:
        del mobile_sessions[t]


def photo_to_pdf(data: bytes) -> bytes:
    """Photo -> PDF d'une page (orientation EXIF corrigée, taille raisonnable)."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((3000, 3000))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    k = PHOTO_LONG_SIDE_PT / max(img.size)
    pdf = fitz.open()
    page = pdf.new_page(width=img.width * k, height=img.height * k)
    page.insert_image(page.rect, stream=buf.getvalue())
    return pdf.tobytes()


@app.post("/api/mobile/sessions")
def mobile_create(request: Request):
    _purge_sessions()
    token = secrets.token_urlsafe(16)
    mobile_sessions[token] = {"created": time.time(), "document": None}
    server = request.scope.get("server")
    port = server[1] if server else (request.url.port or 8000)
    return {"token": token, "url": f"http://{lan_ip()}:{port}/mobile/{token}", "expires_in": SESSION_TTL}


@app.get("/api/mobile/sessions/{token}")
def mobile_status(token: str):
    _purge_sessions()
    s = mobile_sessions.get(token)
    if s is None:
        raise HTTPException(404, "Session expirée.")
    if s["document"] is None:
        return {"status": "waiting"}
    return {"status": "done", "document": s["document"]}


@app.get("/mobile/{token}", response_class=HTMLResponse)
def mobile_page(token: str):
    _purge_sessions()
    s = mobile_sessions.get(token)
    if s is None or s["document"] is not None:
        return HTMLResponse(EXPIRED_HTML, status_code=404)
    return HTMLResponse(MOBILE_HTML.replace("__TOKEN__", token), headers={"Cache-Control": "no-store"})


@app.post("/api/mobile/upload/{token}")
def mobile_upload(token: str, file: UploadFile = File(...)):
    _purge_sessions()
    s = mobile_sessions.get(token)
    if s is None:
        raise HTTPException(404, "Lien expiré. Générez un nouveau QR code dans Lectio.")
    if s["document"] is not None:
        raise HTTPException(410, "Une photo a déjà été envoyée avec ce QR code.")
    data = file.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photo trop volumineuse.")
    try:
        pdf = photo_to_pdf(data)
    except Exception:
        raise HTTPException(400, "Image illisible.")
    s["document"] = register_pdf(pdf, time.strftime("Photo %H:%M"))
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True}


# Production : sert le front compilé (npm run build) si présent
_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
