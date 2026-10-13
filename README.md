# 📖 Lectio

**Lectio** est une application de bureau qui extrait le texte de vos PDF grâce à l'OCR.
Vous pouvez reconnaître **tout le document en un clic**, ou **tracer une zone à la souris**
pour ne lire que l'endroit qui vous intéresse. Le texte obtenu est modifiable, puis validé et exporté.

Tout fonctionne **en local** : vos documents ne quittent jamais votre machine.

---

## ✨ Fonctionnalités

- **Import simple** : glissez-déposez un PDF ou cliquez sur *Charger un PDF*.
- **Visionneuse** : navigation page par page.
- **OCR total** : reconnaissance de toutes les pages, séparées par `--- Page n ---`.
- **OCR par zone** : tracez un rectangle à la souris sur le PDF (un simple clic efface la zone), puis lancez l'OCR sur cette seule zone. Une zone est mémorisée par page.
- **Surlignage sur le PDF** : les éléments de texte détectés sont encadrés en **bleu** ; une fois validés, ils sont surlignés en **vert** et numérotés. Le numéro correspond à celui de la liste des résultats validés.
- **Résultat modifiable** : corrigez le texte directement dans l'application.
- **Validation et export** : validez les résultats un par un, retrouvez-les dans la liste, puis téléchargez-les en `.txt`.
- **Moteur [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)** : reconnaissance en français par défaut, entièrement hors ligne une fois les modèles téléchargés.

---

## 🧱 Architecture

```
┌───────────────────────────── Fenêtre Electron ─────────────────────────────┐
│                                                                            │
│   Interface React + Vite            requêtes /api            API Python    │
│   (visionneuse, sélection,   ───────────────────────────►   FastAPI        │
│    résultat, validation)     ◄───────────────────────────   PyMuPDF        │
│                                   JSON / images              PaddleOCR     │
└────────────────────────────────────────────────────────────────────────────┘
```

| Couche | Technologie | Rôle |
|---|---|---|
| Application de bureau | **Electron** | Fenêtre native ; démarre et arrête l'API Python |
| Interface | **React + Vite** | Visionneuse, tracé de zone, résultat, validation |
| API | **FastAPI** (Python) | Reçoit les PDF, fournit les pages, lance l'OCR |
| Rendu PDF | **PyMuPDF** | Transforme chaque page en image |
| OCR | **PaddleOCR** | Reconnaissance du texte |

Les zones sont échangées en **coordonnées relatives (0 à 1)** : le résultat ne dépend donc pas de la taille d'affichage.

---

## 📁 Structure du projet

```
lectio/
├── environment.yml        # Environnement conda (Python + Node.js + dépendances)
├── Lectio.command         # Lanceur macOS (double-clic)
├── backend/
│   └── main.py            # API FastAPI : PDF, pages, OCR
├── frontend/              # Interface React + Vite
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx        # Écran principal, menu, résultat, validation
│       ├── PdfViewer.jsx  # Affichage de la page + tracé de la zone
│       ├── UploadZone.jsx # Dépôt / chargement du PDF
│       ├── api.js         # Appels à l'API
│       └── styles.css
└── desktop/               # Application de bureau
    ├── package.json
    └── main.js            # Fenêtre Electron + démarrage de l'API Python
```

---

## ✅ Prérequis

- [**conda**](https://docs.conda.io/en/latest/miniconda.html) (Miniconda ou Anaconda)
- Une connexion internet **pour l'installation** et **au premier OCR** (téléchargement des modèles PaddleOCR)

Python 3.11 et Node.js 20 sont installés automatiquement par conda : vous n'avez rien d'autre à installer.

---

## 🚀 Installation (une seule fois)

```bash
cd lectio

# 1. Créer l'environnement (Python 3.11, Node.js 20, PaddleOCR, FastAPI…)
conda env create -f environment.yml
conda activate lectio

# 2. Installer les dépendances JavaScript
cd frontend && npm install && cd ..
cd desktop  && npm install && cd ..
```

> L'environnement `lectio` existe déjà ? Mettez-le à jour avec
> `conda env update -f environment.yml --prune`.

Le `npm install` du dossier `desktop` télécharge Electron (environ 100 Mo).

---

## ▶️ Lancer l'application

### Application de bureau (recommandé)

```bash
conda activate lectio
cd desktop
npm run app
```

`npm run app` compile l'interface puis ouvre la fenêtre. Electron démarre lui-même l'API Python et l'arrête quand vous fermez la fenêtre.

> ⏳ Le tout premier lancement est plus long : PaddleOCR télécharge ses modèles.

### Sur macOS : double-clic

Double-cliquez sur **`Lectio.command`**. Il active l'environnement conda puis lance l'application.
La première fois, il peut être nécessaire de le rendre exécutable :

```bash
chmod +x Lectio.command
```

### Mode développement (navigateur, rechargement à chaud)

Pour modifier l'interface, ouvrez deux terminaux avec l'environnement `lectio` activé :

```bash
# Terminal 1 : l'API
cd backend
python -m uvicorn main:app --port 8000

# Terminal 2 : l'interface
cd frontend
npm run dev          # http://localhost:5173
```

### Mode navigateur « un seul serveur »

```bash
cd frontend && npm run build
cd ../backend && python -m uvicorn main:app --port 8000   # http://localhost:8000
```

---

## 🖱️ Utilisation

1. **Chargez un PDF** (glisser-déposer ou bouton).
2. **Naviguez** entre les pages avec les flèches ◀ ▶ ou le champ de numéro de page.
3. Au choix :
   - cliquez sur **OCR total** pour lire tout le document ;
   - ou **maintenez le clic et glissez** sur le PDF pour tracer une zone, puis cliquez sur **OCR de la zone sélectionnée**.
4. Le texte s'affiche en bas à droite, sous les boutons, et les éléments détectés sont **encadrés en bleu** sur le PDF. **Corrigez le texte** si besoin.
5. Cliquez sur **✅ Valider** : le résultat rejoint la liste des résultats validés et ses éléments sont **surlignés en vert** (numérotés) sur le PDF.
6. Dans la liste, survolez un résultat pour le mettre en évidence sur le PDF, cliquez sur **Voir** pour aller à sa page, ou sur **Retirer** pour le supprimer (le surlignage disparaît).
7. Cliquez sur **Télécharger (.txt)** pour exporter tous les résultats validés.

💡 Un simple clic sur le PDF efface la zone. Le bouton *OCR de la zone* reste grisé tant qu'aucune zone n'est tracée.

---

## ⚙️ Configuration

| Réglage | Où | Valeur par défaut |
|---|---|---|
| Langue de l'OCR | `OCR_LANG` dans `backend/main.py` | `"fr"` |
| Qualité du rendu des pages | `ZOOM` dans `backend/main.py` | `2.0` (≈ 144 dpi) |
| Nombre de PDF gardés en mémoire | `MAX_DOCS` dans `backend/main.py` | `10` |
| Interpréteur Python utilisé par Electron | variable `LECTIO_PYTHON` | `python` (celui de l'env actif) |

Exemple : `LECTIO_PYTHON=/chemin/vers/python npm run app`

---

## 🔌 API (pour les curieux)

| Méthode | Route | Description |
|---|---|---|
| `POST` | `/api/documents` | Envoie un PDF ; renvoie son identifiant et la taille des pages |
| `GET` | `/api/documents/{id}/pages/{n}/image` | Image JPEG de la page `n` (à partir de 1) |
| `POST` | `/api/documents/{id}/ocr` | OCR de tout le document ; renvoie `text` et `lines` (position de chaque ligne détectée) |
| `POST` | `/api/documents/{id}/ocr/zone` | OCR d'une zone `{page, x, y, w, h}` (valeurs de 0 à 1) ; renvoie `text` et `lines` |
| `GET` | `/api/health` | Vérifie que le serveur répond |

La documentation interactive est disponible sur `/docs` quand l'API tourne.

---

## 🛠️ Dépannage

| Problème | Solution |
|---|---|
| `uvicorn: command not found` | L'environnement n'est pas activé : `conda activate lectio`. Utilisez `python -m uvicorn …` |
| Boîte de dialogue « Impossible de lancer python » | Activez l'environnement `lectio` ou renseignez `LECTIO_PYTHON` |
| « L'interface n'est pas compilée » | Lancez `npm run build` dans `frontend/`, ou utilisez `npm run app` |
| Fenêtre bloquée sur « Démarrage du moteur OCR… » | Premier lancement : attendez le téléchargement des modèles. Au-delà de 90 s, une erreur détaillée s'affiche |
| « Document introuvable » | Le serveur a redémarré : rechargez le PDF |
| Une zone ne donne aucun texte | Élargissez-la un peu et évitez de couper les lignes en deux |

---

## 🧭 Limites et pistes d'amélioration

- Seuls les **PDF** sont acceptés pour l'instant (les images pourraient être ajoutées).
- Le surlignage se fait au niveau des **lignes de texte détectées** par PaddleOCR, pas mot à mot. Si vous corrigez le texte, les surlignages ne changent pas.
- Python n'est pas embarqué : l'environnement conda `lectio` est nécessaire pour lancer l'application.
- Idées : surlignage mot à mot, lien entre une ligne du texte et sa place sur le PDF, zoom, export PDF « interrogeable », empaquetage en `.app` / `.dmg`.

---

## 🙏 Crédits

[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) · [FastAPI](https://fastapi.tiangolo.com/) · [PyMuPDF](https://pymupdf.readthedocs.io/) · [React](https://react.dev/) · [Vite](https://vitejs.dev/) · [Electron](https://www.electronjs.org/)
