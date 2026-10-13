"""
Lectio – API (FastAPI + PyMuPDF + PaddleOCR)

Lancement (depuis le dossier backend/) :
    uvicorn main:app --port 8000
"""

import io
import threading
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
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


@app.post("/api/documents")
def upload(file: UploadFile = File(...)):
    data = file.file.read()
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
    return {"id": doc_id, "name": file.filename, "pages": pages}


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


@app.get("/api/health")
def health():
    return {"ok": True}


# Production : sert le front compilé (npm run build) si présent
_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
