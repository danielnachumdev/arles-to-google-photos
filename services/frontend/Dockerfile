# syntax=docker/dockerfile:1

FROM node:22-alpine AS build

WORKDIR /app

# Semver baked at CD into the SPA bundle (fallback when /api/version is unavailable).
ARG ARLES_VERSION=
ENV VITE_APP_VERSION=${ARLES_VERSION}

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.31.9-alpine

ARG ARLES_VERSION=
ARG BUILD_TIME=
ENV ARLES_VERSION=${ARLES_VERSION} \
    BUILD_TIME=${BUILD_TIME}

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
