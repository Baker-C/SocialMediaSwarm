// Production server: serves the built SPA and proxies /api to the backend.
// In dev, react-scripts + src/setupProxy.js handle this instead.
const path = require('path');
const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const { SocksProxyAgent } = require('socks-proxy-agent');

const PORT = process.env.PORT || 3000;
const target = process.env.REACT_APP_PROXY_TARGET || 'http://127.0.0.1:8000';
// ponytail: userspace-mode tailscale installs no kernel routes, so reach the
// tailnet backend through tailscaled's SOCKS5 proxy (socks5h = remote DNS, so
// MagicDNS names resolve). Unset TS_SOCKS5_PROXY to dial the target directly.
const socks = process.env.TS_SOCKS5_PROXY;
const agent = socks ? new SocksProxyAgent(socks) : undefined;

const build = path.join(__dirname, 'build');
const app = express();

app.use('/api', createProxyMiddleware({ target, changeOrigin: true, agent }));
app.use(express.static(build));
app.get('*', (_req, res) => res.sendFile(path.join(build, 'index.html')));

app.listen(PORT, '0.0.0.0', () =>
  console.log(`frontend on :${PORT}  /api -> ${target}${socks ? ` via ${socks}` : ''}`)
);
