#!/bin/sh
tailscaled --tun=userspace-networking &
sleep 2
tailscale up --authkey="$TAILSCALE_AUTHKEY" --hostname=render-frontend
npm start
