#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
domain="${1:-}"
if [[ ${#domain} -gt 253 || ! "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$ ]]; then
    echo 'Usage: bash scripts/configure-traefik.sh test.your-domain.nl' >&2
    exit 1
fi
IFS='.' read -r -a labels <<< "$domain"
for label in "${labels[@]}"; do
    if [[ ${#label} -gt 63 ]]; then
        echo 'A DNS label may not exceed 63 characters.' >&2
        exit 1
    fi
done

target=traefik/routes.yml
if [[ -e "$target" || -L "$target" ]]; then
    echo 'Traefik routes already exist. Edit them instead of overwriting them.' >&2
    exit 1
fi
( set -o noclobber; sed "s/__TEST_DOMAIN__/$domain/g" traefik/routes.yml.template > "$target" )
echo "Traefik routes created for $domain. Set ACME_EMAIL in .env before starting Compose."
