#!/bin/sh
if [ -n "$TAILSCALE_AUTHKEY" ]; then
  tailscaled --tun=userspace-networking &
  sleep 2
  tailscale up --authkey="$TAILSCALE_AUTHKEY" --hostname=render-frontend || true
fi
npm start
