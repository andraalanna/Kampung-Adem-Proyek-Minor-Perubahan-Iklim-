# Builds the React dashboard and serves it with Caddy (TLS via Let's Encrypt) + reverse proxy.
FROM node:22-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /src/dist /srv
