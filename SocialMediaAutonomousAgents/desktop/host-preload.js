// Host-window preload. The dashboard is served over http with contextIsolation
// on, so `window.process` is not exposed to the renderer. Expose a single, safe
// boolean the dashboard can read to know it is running inside the desktop shell
// (so SignupWebview renders the <webview> instead of the fallback note).
const { contextBridge } = require("electron");

try {
  contextBridge.exposeInMainWorld("xprovDesktop", true);
} catch (_e) {
  // contextBridge should always exist with contextIsolation:true; ignore otherwise.
}
