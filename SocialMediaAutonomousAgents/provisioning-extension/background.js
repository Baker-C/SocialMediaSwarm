// Service worker: the ONLY place network calls to the backend happen. Content
// scripts run in the x.com origin and would hit CORS; the worker uses the
// extension origin + host_permissions, so it can call the backend freely.

function getConfig() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["backendUrl", "agentToken", "accountId"], resolve);
  });
}

async function api(path, { method = "GET" } = {}) {
  const cfg = await getConfig();
  if (!cfg.backendUrl || !cfg.agentToken || !cfg.accountId) {
    throw new Error("Extension not configured (open the popup).");
  }
  const base = cfg.backendUrl.replace(/\/$/, "");
  const url = `${base}/provisioning/${encodeURIComponent(cfg.accountId)}${path}`;
  const resp = await fetch(url, {
    method,
    headers: { Authorization: `Bearer ${cfg.agentToken}` },
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${path}`);
  return resp.json();
}

function genPassword() {
  // Strong-enough throwaway password: letters + digits + symbols, 16 chars.
  const sets = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%";
  const arr = new Uint32Array(16);
  crypto.getRandomValues(arr);
  return Array.from(arr, (n) => sets[n % sets.length]).join("");
}

const HANDLERS = {
  job: () => api("/job"),
  emailCode: () => api("/email-code"),
  acquirePhone: () => api("/phone", { method: "POST" }),
  smsCode: () => api("/phone-code"),
  password: async () => ({ password: genPassword() }),
};

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const handler = HANDLERS[msg?.type];
  if (!handler) {
    sendResponse({ ok: false, error: `unknown request: ${msg?.type}` });
    return false;
  }
  handler()
    .then((data) => sendResponse({ ok: true, data }))
    .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
  return true; // keep the message channel open for the async response
});
