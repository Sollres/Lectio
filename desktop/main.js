/**
 * Lectio – coque Electron
 * 1. lance l'API Python (uvicorn) sur un port libre
 * 2. attend qu'elle réponde
 * 3. ouvre une fenêtre native qui affiche l'interface (frontend/dist servi par l'API)
 */
const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const BACKEND = path.join(ROOT, "backend");
const DIST = path.join(ROOT, "frontend", "dist");
const PYTHON = process.env.LECTIO_PYTHON || "python"; // celui de l'env conda activé

const LOADING_HTML = `<!doctype html><meta charset="utf-8">
<body style="margin:0;height:100vh;display:grid;place-items:center;background:#f4f5f7;
font-family:system-ui,sans-serif;color:#1f2430">
<div style="text-align:center"><div style="font-size:48px">📖</div>
<h2 style="margin:8px 0">Lectio</h2><p style="color:#6b7280">Démarrage du moteur OCR…</p></div>`;

let win = null;
let py = null;
let spawnError = null;
let stderrTail = "";

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

// 0.0.0.0 : nécessaire pour que le téléphone atteigne la page photo (le reste de l'API reste
// réservé à cet ordinateur, voir lan_guard dans backend/main.py)
function startBackend(port) {
  py = spawn(
    PYTHON,
    ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", String(port)],
    { cwd: BACKEND }
  );
  py.stderr.on("data", (d) => {
    stderrTail = (stderrTail + d.toString()).slice(-2000);
  });
  py.on("error", (err) => {
    spawnError = `Impossible de lancer « ${PYTHON} » : ${err.message}`;
  });
}

function stopBackend() {
  if (py && py.exitCode === null) py.kill();
}

function waitForServer(port, timeoutMs = 90000) {
  const t0 = Date.now();
  return new Promise((resolve, reject) => {
    const retry = () => {
      if (Date.now() - t0 > timeoutMs) {
        reject(new Error("Le serveur Python ne répond pas.\n\n" + stderrTail));
      } else {
        setTimeout(tryOnce, 400);
      }
    };
    const tryOnce = () => {
      if (spawnError) return reject(new Error(spawnError));
      if (py && py.exitCode !== null) {
        return reject(new Error("Le serveur Python s'est arrêté.\n\n" + stderrTail));
      }
      const req = http.get(
        { host: "127.0.0.1", port, path: "/api/health", timeout: 1000 },
        (res) => {
          res.resume();
          if (res.statusCode === 200) resolve();
          else retry();
        }
      );
      req.on("error", retry);
      req.on("timeout", () => req.destroy());
    };
    tryOnce();
  });
}

async function createWindow() {
  win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: "Lectio",
    backgroundColor: "#f4f5f7",
    webPreferences: { contextIsolation: true },
  });
  win.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(LOADING_HTML));

  try {
    if (!fs.existsSync(path.join(DIST, "index.html"))) {
      throw new Error(
        "L'interface n'est pas compilée.\nLancez « npm run build » dans frontend/ (ou « npm run app » ici)."
      );
    }
    const port = await freePort();
    startBackend(port);
    await waitForServer(port);
    if (!win.isDestroyed()) await win.loadURL(`http://127.0.0.1:${port}`);
  } catch (err) {
    dialog.showErrorBox("Lectio – démarrage impossible", err.message);
    app.quit();
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(createWindow);
  app.on("window-all-closed", () => app.quit());
  app.on("will-quit", stopBackend);
  process.on("exit", stopBackend);
}
