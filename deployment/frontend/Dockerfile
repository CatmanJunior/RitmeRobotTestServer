FROM nginx:1.28-alpine

ENV NGINX_ENVSUBST_FILTER="^BACKEND_UPSTREAM$"

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY dist/ /usr/share/nginx/html/

EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=12 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
