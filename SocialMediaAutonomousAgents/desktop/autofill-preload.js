// <webview> preload — runs INSIDE the x.com guest page.
//
// Shows this account's provisioning info in a floating modal (email, phone,
// generated password, and incoming verification codes as they arrive), autofills
// the signup fields from the backend, and polls for SMS/email codes live. It NEVER
// clicks Next or submits — the operator clicks through and solves the Arkose CAPTCHA.
//
// Account id is passed via the webview URL hash (#xprov=<accountId>), so each
// preload instance is bound to the account whose persist:acct_<id> partition this
// webview runs in.

const { ipcRenderer } = require("electron");

// ---- React-safe field fill --------------------------------------------------
function fill(selectors, value) {
  const el = selectors
    .map((s) => document.querySelector(s))
    .find((e) => e && e.offsetParent !== null); // first visible match
  if (!el) return false;
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  el.focus();
  setter.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

// React-safe <select> set: native value setter + change event so React state updates.
function selectValue(selectors, value) {
  const el = selectors.map((s) => document.querySelector(s)).find((e) => e && e.offsetParent !== null);
  if (!el) return false;
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set;
  el.focus();
  setter.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

const FIELD = {
  name: ['input[name="name"]', 'input[autocomplete="name"]'],
  email: ['input[name="email"]', 'input[autocomplete="email"]', 'input[type="email"]'],
  password: ['input[name="password"]', 'input[type="password"]'],
  code: [
    'input[autocomplete="one-time-code"]',
    'input[name="verfication_code"]',
    'input[name="verification_code"]',
    'input[inputmode="numeric"]',
  ],
  phone: ['input[name="phone_number"]', 'input[autocomplete="tel"]', 'input[type="tel"]'],
  // Date-of-birth <select> dropdowns (captured from the real signup DOM).
  dobMonth: ['#jf-date-date_of_birth-month', 'select[name="date_of_birth-month"]'],
  dobDay: ['#jf-date-date_of_birth-day', 'select[name="date_of_birth-day"]'],
  dobYear: ['#jf-date-date_of_birth-year', 'select[name="date_of_birth-year"]'],
};

// ---- account id from URL hash ----------------------------------------------
function accountId() {
  // The id arrives in the URL hash (#xprov=<id>) on first load, but X's signup
  // navigation drops the hash. Cache it in this partition's localStorage (which
  // is per-account, since the webview uses persist:acct_<id>) and fall back to it.
  const m = /[#&]xprov=([^&]+)/.exec(location.hash || "");
  if (m) {
    const id = decodeURIComponent(m[1]);
    try {
      localStorage.setItem("__xprov_account", id);
    } catch (_e) {
      /* ignore */
    }
    return id;
  }
  try {
    return localStorage.getItem("__xprov_account") || "";
  } catch (_e) {
    return "";
  }
}

// ---- IPC to main ------------------------------------------------------------
async function ask(action, value) {
  const res = await ipcRenderer.invoke("prov:action", { action, accountId: accountId(), value });
  if (!res || !res.ok) throw new Error((res && res.error) || "ipc failed");
  return res.data;
}

let _job = null;
async function job() {
  if (_job) return _job;
  _job = await ask("getJob");
  return _job;
}

// ---- info modal: email / phone / password / live codes ----------------------
let refs = null;
function ensurePanel() {
  if (refs || !document.documentElement) return;
  const panel = document.createElement("div");
  panel.style.cssText =
    "position:fixed;top:12px;right:12px;z-index:2147483647;background:#0b0b0c;color:#eee;" +
    "font:12px system-ui,sans-serif;border:1px solid #333;border-radius:8px;padding:10px;width:290px;" +
    "box-shadow:0 6px 24px rgba(0,0,0,.5)";
  const row = (label, id) =>
    '<div style="margin-bottom:4px;word-break:break-all"><b>' +
    label +
    ':</b> <span id="' +
    id +
    '" style="color:#9cf">…</span></div>';
  panel.innerHTML =
    '<div style="font-weight:600;margin-bottom:6px">X Provisioning — ' +
    (accountId() || "?") +
    "</div>" +
    row("Email", "xp-email") +
    '<div style="margin-bottom:6px"><b>Phone (rental # for this account):</b><br>' +
    '<input id="xp-phone-input" placeholder="e.g. 6204081380" style="width:60%;padding:4px;margin-top:2px;' +
    'background:#161618;border:1px solid #333;color:#eee;border-radius:4px"/>' +
    '<button id="xp-phone-set" style="width:36%;margin-left:3%;padding:5px;background:#16a34a;color:#fff;' +
    'border:none;border-radius:4px;cursor:pointer;font-weight:600">Use #</button></div>' +
    row("Password", "xp-pass") +
    '<div style="margin-bottom:4px"><b>Codes:</b> ' +
    '<span id="xp-codes" style="color:#7f7">(waiting…)</span></div>' +
    '<div id="xp-status" style="font-size:11px;color:#7c7;min-height:16px;margin-top:4px">starting…</div>' +
    '<button id="xp-recheck" style="margin-top:6px;width:100%;padding:6px;background:#2563eb;' +
    'color:#fff;border:none;border-radius:4px;cursor:pointer;font-weight:600">↻ Re-check (poll for code/number)</button>' +
    '<button id="xp-capture" style="margin-top:6px;width:100%;padding:6px;background:#f60;' +
    'color:#111;border:none;border-radius:4px;cursor:pointer;font-weight:600">Capture screen for Claude</button>';
  document.documentElement.appendChild(panel);
  refs = {
    email: panel.querySelector("#xp-email"),
    phoneInput: panel.querySelector("#xp-phone-input"),
    pass: panel.querySelector("#xp-pass"),
    codes: panel.querySelector("#xp-codes"),
    status: panel.querySelector("#xp-status"),
  };
  const btn = panel.querySelector("#xp-capture");
  if (btn) btn.addEventListener("click", () => capture("manual"));
  const rb = panel.querySelector("#xp-recheck");
  if (rb) rb.addEventListener("click", () => void recheck());
  const sb = panel.querySelector("#xp-phone-set");
  if (sb) sb.addEventListener("click", () => void assignPhone(refs.phoneInput && refs.phoneInput.value));
}
function setRow(key, text) {
  ensurePanel();
  if (refs && refs[key]) refs[key].textContent = text;
}
function setStatus(text) {
  setRow("status", text);
}

// ---- DOM capture for selector debugging -------------------------------------
function capture(label) {
  try {
    const html = document.documentElement ? document.documentElement.outerHTML : "";
    void ipcRenderer.invoke("prov:capture", {
      accountId: accountId(),
      label: label || "screen",
      url: location.href,
      html,
    });
    setStatus("captured: " + (label || "screen"));
  } catch (e) {
    setStatus("capture error: " + e.message);
  }
}

// ---- live verification codes ------------------------------------------------
const seenCodes = new Set();
function addCode(code) {
  if (!code || seenCodes.has(code)) return;
  seenCodes.add(code);
  setRow("codes", Array.from(seenCodes).join("   "));
}

// ---- per-account identity (idempotent; shown in the modal) ------------------
let _phone = null;
let _pass = null;
async function showEmail() {
  try {
    setRow("email", (await job()).email || "(none)");
  } catch (e) {
    setRow("email", "error: " + e.message);
  }
}
// Load this account's persistent (rental) number from the backend and prefill the
// modal input. No number is acquired — the operator assigns one with "Use #".
async function loadPhone() {
  if (_phone) return _phone;
  try {
    const r = await ask("getPhone");
    _phone = (r && r.phone) || null;
    if (_phone && refs && refs.phoneInput && !refs.phoneInput.value) {
      refs.phoneInput.value = _phone;
    }
  } catch (e) {
    setStatus("phone load error: " + e.message);
  }
  return _phone;
}

// Operator-entered rental number → persist it per account, then re-run autofill so
// X's phone field gets it and the SMS poll listens on it.
async function assignPhone(value) {
  const v = String(value || "").trim();
  if (!v) {
    setStatus("enter the rental number first");
    return;
  }
  try {
    const r = await ask("setPhone", v);
    _phone = (r && r.phone) || v;
    filled.phone = false; // allow X's phone field to be (re)filled with the new number
    if (refs && refs.phoneInput) refs.phoneInput.value = _phone;
    setStatus("number set for this account: " + _phone);
    void scan();
  } catch (e) {
    setStatus("set phone error: " + e.message);
  }
}
async function ensurePassword() {
  if (_pass) return _pass;
  try {
    // Prefer the account's fixed/shared password carried on the job; only fall
    // back to generating one if the job has none.
    const jobPass = (await job()).password;
    _pass = jobPass || (await ask("genPassword")).password;
    setRow("pass", _pass);
  } catch (e) {
    setRow("pass", "error: " + e.message);
  }
  return _pass;
}

// ---- autofill ---------------------------------------------------------------
const filled = { name: false, email: false, password: false, code: false, phone: false, dob: false };
function visible(selectors) {
  return selectors.some((s) => {
    const e = document.querySelector(s);
    return e && e.offsetParent !== null;
  });
}
async function tryFillBasics() {
  if ((!filled.name && visible(FIELD.name)) || (!filled.email && visible(FIELD.email))) {
    try {
      const j = await job();
      if (!filled.name && fill(FIELD.name, j.display_name)) filled.name = true;
      if (!filled.email && fill(FIELD.email, j.email)) filled.email = true;
    } catch (e) {
      setStatus("error (job): " + e.message);
    }
  }
  if (!filled.password && visible(FIELD.password)) {
    const pw = await ensurePassword();
    if (pw && fill(FIELD.password, pw)) {
      filled.password = true;
      setStatus("password filled");
    }
  }
}
async function tryFillPhone() {
  if (filled.phone || !visible(FIELD.phone)) return;
  const p = _phone || (await loadPhone());
  if (p && fill(FIELD.phone, p)) {
    filled.phone = true;
    setStatus("phone filled: " + p);
  }
}
async function tryFillCode() {
  if (filled.code || !visible(FIELD.code)) return;
  for (const action of ["emailCode", "smsCode"]) {
    try {
      const data = await ask(action);
      if (data && data.code) {
        addCode(data.code);
        if (fill(FIELD.code, data.code)) {
          filled.code = true;
          setStatus("code filled (" + action + "): " + data.code);
          return;
        }
      }
    } catch (e) {
      // not ready — keep polling
    }
  }
}
// Date of birth: fixed adult DOB with year 2000 (X requires all three selects).
function tryFillDob() {
  if (filled.dob || !visible(FIELD.dobYear)) return;
  const m = selectValue(FIELD.dobMonth, "6"); // June
  const d = selectValue(FIELD.dobDay, "15");
  const y = selectValue(FIELD.dobYear, "2000");
  if (y) {
    filled.dob = true;
    setStatus(`DOB set: 2000-06-15 (m:${m} d:${d})`);
  }
}

let running = false;
async function scan() {
  if (running) return; // serialize; observer can fire rapidly
  running = true;
  try {
    await tryFillBasics();
    tryFillDob();
    await tryFillPhone();
    await tryFillCode();
  } finally {
    running = false;
  }
}

// Manual re-check: re-poll the code endpoints now and re-run the autofill scan.
// Does NOT reset anything — scan() honors the `filled` flags and ensurePhone()
// is idempotent, so this only picks up newly-arrived data (e.g. the SMS code).
async function recheck() {
  setStatus("re-checking…");
  for (const action of ["emailCode", "smsCode"]) {
    try {
      const d = await ask(action);
      if (d && d.code) addCode(d.code);
    } catch (e) {
      /* not ready */
    }
  }
  await scan();
  setStatus("re-checked");
}

// ---- live code polling (drives the modal Codes row) -------------------------
function startCodePolling() {
  setInterval(async () => {
    for (const action of ["emailCode", "smsCode"]) {
      try {
        const d = await ask(action);
        if (d && d.code) addCode(d.code);
      } catch (e) {
        // no inbox/lease yet, or no code — ignore
      }
    }
  }, 4000);
}

function isSignupFlow() {
  const host = location.hostname || "";
  return /(^|\.)x\.com$/.test(host) || /(^|\.)twitter\.com$/.test(host);
}

function start() {
  if (!isSignupFlow()) return;
  ensurePanel();
  setStatus("watching for fields…");
  // Populate the modal with this account's identity up front.
  void showEmail();
  void loadPhone();
  void ensurePassword();
  // Autofill loop.
  void scan();
  const obs = new MutationObserver(() => void scan());
  obs.observe(document.documentElement, { childList: true, subtree: true });
  // Live verification codes into the modal.
  startCodePolling();
  // Auto-capture the DOM whenever the URL changes (SPA nav).
  let lastUrl = location.href;
  capture("nav");
  setInterval(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      capture("nav");
    }
  }, 1500);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}
