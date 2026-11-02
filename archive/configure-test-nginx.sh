#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
domain="${1:-}"
if [[ ! "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ || "$domain" != *.* ]]; then
    echo 'Usage: sudo bash scripts/configure-nginx.sh test.your-domain.nl' >&2
    exit 1
fi
site=/etc/nginx/sites-available/ritmerobot-test.conf
enabled=/etc/nginx/sites-enabled/ritmerobot-test.conf
if [[ -e "$site" || -L "$site" || -e "$enabled" || -L "$enabled" ]]; then
    echo 'A ritmerobot-test Nginx site already exists. Edit that site instead of overwriting it.' >&2
    exit 1
fi
sed "s/__TEST_DOMAIN__/$domain/g" nginx.conf.template > "$site"
ln -s "$site" "$enabled"
if ! nginx -t; then
    rm -f "$enabled" "$site"
    echo 'Nginx check failed; the newly created test-site configuration was removed.' >&2
    exit 1
fi
systemctl reload nginx
echo "HTTP test site configured for $domain. Next: sudo certbot --nginx -d $domain --redirect"
