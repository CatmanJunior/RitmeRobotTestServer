#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
if [[ -s backend.env ]]; then
    echo 'backend.env already exists. Keep it: replacing keys would invalidate sessions and encrypted email data.' >&2
    exit 1
fi
: > backend.env
chmod 600 backend.env
mkdir -p data
generated="$(mktemp .backend.env.XXXXXXXX)"
trap 'rm -f "$generated"' EXIT
docker compose run --rm -T --no-deps backend python - > "$generated" <<'PY'
import json
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

key = ec.generate_private_key(ec.SECP384R1())
values = {
    "JWT_ALGORITHM": "ES384",
    "JWT_PRIVATE_KEY": key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode(),
    "JWT_PUBLIC_KEY": key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode(),
    "EMAIL_FERNET": Fernet.generate_key().decode(),
    "BACKUP_INTERVAL": "86400",
    "BACKUP_RETENTION": "10",
}
for name, value in values.items():
    print(f"{name}={json.dumps(value)}")
PY
test -s "$generated"
mv "$generated" backend.env
chmod 600 backend.env
docker compose run --rm -T --no-deps backend python -c 'from jwt import create_token, decode_token; from emails import cipher_suite; assert decode_token(create_token("configuration-check"))["sub"] == "configuration-check"; print("Signing and encryption configuration validated.")'
echo 'Fresh test keys generated. Backend loads backend.env as a file; do not pass it through Docker --env-file.'
