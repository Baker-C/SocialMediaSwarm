FROM node:22-alpine

RUN apk add --no-cache tailscale iproute2

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 3000
CMD ["/start.sh"]
