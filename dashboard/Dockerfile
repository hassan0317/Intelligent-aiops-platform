# Multi-stage: build the React/Tremor SPA with Node, serve static files with nginx.
FROM node:20-alpine AS build
WORKDIR /app
# Locked, reproducible install: npm ci installs the exact tree from package-lock.json
# (fails if the lock is out of sync), so the build is identical on every clone.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
