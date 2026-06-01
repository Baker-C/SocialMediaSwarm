const { createProxyMiddleware } = require('http-proxy-middleware');

/** Proxy /api only (not all unmatched dev-server paths). */
module.exports = function setupProxy(app) {
  const target = process.env.REACT_APP_PROXY_TARGET || 'http://127.0.0.1:8000';
  app.use(
    '/api',
    createProxyMiddleware({
      target,
      changeOrigin: true,
    })
  );
};
