#!/bin/sh
set -e
if [ -n "$TAILSCALE_AUTHKEY" ]; then
  tailscaled --tun=userspace-networking --socks5-server=localhost:1055 &
  # Bring up the tailnet in the background so the web server binds $PORT immediately
  # (Render kills the container if no port opens). /api just fails until it's up.
  ( sleep 2; tailscale up --authkey="$TAILSCALE_AUTHKEY" --hostname=render-frontend || true ) &
  export TS_SOCKS5_PROXY="socks5h://127.0.0.1:1055"
fi
exec node server.js
