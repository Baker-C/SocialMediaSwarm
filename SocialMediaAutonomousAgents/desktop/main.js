// Electron main process for the X-signup provisioning shell.
//
// It opens the dashboard in a BrowserWindow with <webview> enabled, and acts as
// the single place that talks to the backend: the webview preload calls us over
// IPC, we attach the agent token + hit the backend, and return JSON. Keeping the
// token (and the fetch) in main avoids CORS and never exposes the token to the
// guest x.com page.

const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");

// Incrementing sequence so DOM captures sort in the order they were taken.
let _capSeq = 0;

// Absolute path to the webview preload. Main injects this into every <webview>
// via will-attach-webview, so the renderer (served over http from the dashboard)
// doesn't need to construct a file:// path itself.
const PRELOAD_PATH = path.join(__dirname, "autofill-preload.js");

const DASHBOARD_URL = (process.env.DASHBOARD_URL || "http://localhost:3000").replace(/\/$/, "");
const BACKEND_URL = (process.env.BACKEND_URL || "http://localhost:8000/api").replace(/\/$/, "");
const AGENT_TOKEN = process.env.PROVISIONING_AGENT_TOKEN || "";

// ---- backend bridge ---------------------------------------------------------

async function backend(path, { method = "GET", body = null } = {}) {
  if (!AGENT_TOKEN) {
    throw new Error("PROVISIONING_AGENT_TOKEN is not set in the Electron environment");
  }
  const opts = { method, headers: { Authorization: `Bearer ${AGENT_TOKEN}` } };
  if (body != null) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(`${BACKEND_URL}${path}`, opts);
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status} for ${path}`);
  }
  return resp.json();
}

function genPassword() {
  // Strong-enough throwaway password: letters + digits + symbols, 16 chars.
  // Mirrors provisioning-extension/background.js so behavior is identical.
  const sets = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%";
  const { randomBytes } = require("crypto");
  const arr = randomBytes(16);
  let out = "";
  for (const n of arr) out += sets[n % sets.length];
  return out;
}

// Same endpoints the extension's background.js uses, keyed per account id.
const PROV = (id) => `/provisioning/${encodeURIComponent(id)}`;

const HANDLERS = {
  getJob: (id) => backend(`${PROV(id)}/job`),
  emailCode: (id) => backend(`${PROV(id)}/email-code`),
  getPhone: (id) => backend(`${PROV(id)}/phone`),
  setPhone: (id, value) => backend(`${PROV(id)}/phone`, { method: "POST", body: { phone: value } }),
  smsCode: (id) => backend(`${PROV(id)}/phone-code`),
  genPassword: async () => ({ password: genPassword() }),
  // Authorize URL so the webview can navigate to consent IN THE SAME partition.
  authorizeUrl: (id) => backend(`/oauth/x/authorize?account_id=${encodeURIComponent(id)}`),
};

function registerIpc() {
  // DOM capture: the preload sends the live page HTML; we write it under
  // desktop/captures/ so the real signup DOM can be read and selectors refined.
  ipcMain.handle("prov:capture", (_event, payload) => {
    try {
      const dir = path.join(__dirname, "captures");
      fs.mkdirSync(dir, { recursive: true });
      const safe = (s, d) => String(s || d).replace(/[^a-z0-9._-]/gi, "_").slice(0, 60);
      _capSeq += 1;
      const seq = String(_capSeq).padStart(3, "0");
      const file = path.join(
        dir,
        `${safe(payload && payload.accountId, "acct")}-${seq}-${safe(payload && payload.label, "screen")}.html`,
      );
      const header = `<!-- url: ${(payload && payload.url) || ""} -->\n`;
      fs.writeFileSync(file, header + ((payload && payload.html) || ""), "utf8");
      return { ok: true, file };
    } catch (err) {
      return { ok: false, error: String((err && err.message) || err) };
    }
  });

  // The preload invokes "prov:action" with { action, accountId }.
  ipcMain.handle("prov:action", async (_event, payload) => {
    const action = payload && payload.action;
    const accountId = payload && payload.accountId;
    const value = payload && payload.value;
    const handler = HANDLERS[action];
    if (!handler) {
      return { ok: false, error: `unknown action: ${action}` };
    }
    if (action !== "genPassword" && !accountId) {
      return { ok: false, error: `action ${action} requires accountId` };
    }
    try {
      const data = await handler(accountId, value);
      return { ok: true, data };
    } catch (err) {
      return { ok: false, error: String((err && err.message) || err) };
    }
  });
}

// ---- window -----------------------------------------------------------------

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 900,
    webPreferences: {
      // Host preload exposes window.xprovDesktop so the dashboard can reliably
      // detect the desktop shell even with contextIsolation on.
      preload: path.join(__dirname, "host-preload.js"),
      webviewTag: true,
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Force OUR preload onto every <webview> the dashboard creates, regardless of
  // the preload attribute the renderer sets (the renderer can't build a trusted
  // file:// path; main owns it). Keep node integration off in the guest.
  win.webContents.on("will-attach-webview", (_event, webPreferences, params) => {
    const src = (params && params.src) || "";
    // Only the signup webview gets the autofill preload (it needs require() + the
    // page DOM, so contextIsolation is off). The HQ/view-only webview gets no
    // preload and stays sandboxed.
    if (/xprov=|i\/flow\/signup/.test(src)) {
      webPreferences.preload = PRELOAD_PATH;
      webPreferences.nodeIntegration = false;
      webPreferences.contextIsolation = false;
    } else {
      webPreferences.nodeIntegration = false;
      webPreferences.contextIsolation = true;
    }
  });

  win.loadURL(DASHBOARD_URL);
}

app.whenReady().then(() => {
  registerIpc();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
