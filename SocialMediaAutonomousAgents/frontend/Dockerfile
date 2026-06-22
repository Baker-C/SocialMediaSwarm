FROM node:22-alpine

RUN apk add --no-cache tailscale iproute2 dos2unix

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

COPY start.sh /start.sh
RUN dos2unix /start.sh && chmod +x /start.sh

EXPOSE 3000
CMD ["/start.sh"]
