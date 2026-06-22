// Injects a floating control panel on x.com. You navigate the signup yourself and
// solve the CAPTCHA; each button pulls data from the backend (via the service
// worker) and fills the matching field on the CURRENT page. Nothing here drives
// navigation or clicks submit — X sees a normal human in a normal browser.

(function () {
  if (window.__xProvPanel) return; // guard against double-injection
  window.__xProvPanel = true;

  // ---- React-safe field fill: set value via the native setter, then fire input ----
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
  };

  function ask(type) {
    return new Promise((resolve) => chrome.runtime.sendMessage({ type }, resolve));
  }

  // ---- panel UI ----
  const panel = document.createElement("div");
  panel.style.cssText =
    "position:fixed;top:12px;right:12px;z-index:2147483647;background:#0b0b0c;color:#eee;" +
    "font:13px system-ui,sans-serif;border:1px solid #333;border-radius:8px;padding:10px;width:230px;" +
    "box-shadow:0 6px 24px rgba(0,0,0,.5)";
  panel.innerHTML =
    '<div style="font-weight:600;margin-bottom:6px">X Provisioning Autofill</div>' +
    '<div id="xp-status" style="font-size:11px;color:#7c7;min-height:28px;margin-bottom:6px">ready</div>';

  const buttons = [
    ["Fill name", async (s) => fill(FIELD.name, (await job()).display_name) ? "name filled" : "no name field"],
    ["Fill email", async (s) => fill(FIELD.email, (await job()).email) ? "email filled" : "no email field"],
    ["Gen + fill password", async () => {
      const r = await ask("password");
      if (!r?.ok) throw new Error(r?.error);
      const pw = r.data.password;
      const ok = fill(FIELD.password, pw);
      navigator.clipboard?.writeText(pw).catch(() => {});
      return ok ? `password filled + copied: ${pw}` : `no field. password (copied): ${pw}`;
    }],
    ["Get email code + fill", async () => {
      const r = await ask("emailCode");
      if (!r?.ok) throw new Error(r?.error);
      const c = r.data.code;
      if (!c) return "no email code yet — retry";
      return fill(FIELD.code, c) ? `email code filled: ${c}` : `no code field. code: ${c}`;
    }],
    ["Acquire phone + fill", async () => {
      const r = await ask("acquirePhone");
      if (!r?.ok) throw new Error(r?.error);
      const p = r.data.phone;
      return fill(FIELD.phone, p) ? `phone filled: ${p}` : `no phone field. phone: ${p}`;
    }],
    ["Get SMS code + fill", async () => {
      const r = await ask("smsCode");
      if (!r?.ok) throw new Error(r?.error);
      const c = r.data.code;
      if (!c) return "no SMS code yet — retry";
      return fill(FIELD.code, c) ? `SMS code filled: ${c}` : `no code field. code: ${c}`;
    }],
  ];

  // Cache the job (email + display name) so repeated fills don't re-hit the backend.
  let _job = null;
  async function job() {
    if (_job) return _job;
    const r = await ask("job");
    if (!r?.ok) throw new Error(r?.error);
    _job = r.data;
    return _job;
  }

  const status = () => panel.querySelector("#xp-status");

  for (const [label, fn] of buttons) {
    const b = document.createElement("button");
    b.textContent = label;
    b.style.cssText =
      "display:block;width:100%;margin:3px 0;padding:6px;background:#161618;color:#eee;" +
      "border:1px solid #333;border-radius:4px;cursor:pointer;text-align:left";
    b.addEventListener("click", async () => {
      status().textContent = "…";
      try {
        status().textContent = (await fn()) || "done";
      } catch (e) {
        status().textContent = "error: " + (e.message || e);
      }
    });
    panel.appendChild(b);
  }

  document.documentElement.appendChild(panel);
})();
