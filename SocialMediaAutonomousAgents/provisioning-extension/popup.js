// Config UI: persists backend URL, agent token, and the target account id to
// chrome.storage.local. The content script + background read from the same store.
const FIELDS = ["backendUrl", "agentToken", "accountId"];
const DEFAULTS = { backendUrl: "http://localhost:8000/api" };

function load() {
  chrome.storage.local.get(FIELDS, (cfg) => {
    for (const f of FIELDS) {
      document.getElementById(f).value = cfg[f] ?? DEFAULTS[f] ?? "";
    }
  });
}

document.getElementById("save").addEventListener("click", () => {
  const cfg = {};
  for (const f of FIELDS) cfg[f] = document.getElementById(f).value.trim();
  chrome.storage.local.set(cfg, () => {
    const s = document.getElementById("status");
    s.textContent = "Saved.";
    setTimeout(() => (s.textContent = ""), 1500);
  });
});

load();
