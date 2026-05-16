# syntax=docker/dockerfile:1

FROM node:20-alpine AS frontend-build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install

COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    UPLOAD_DIR=/app/backend/uploads

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
COPY --from=frontend-build /app/dist /usr/share/nginx/html

RUN chmod +x /app/docker-entrypoint.sh \
    && mkdir -p /app/backend/uploads

EXPOSE 80

CMD ["/app/docker-entrypoint.sh"]
