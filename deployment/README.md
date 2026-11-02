# RitmeRobot VPS test environment

This test bundle targets a fresh Ubuntu 24.04 LTS VPS and a test hostname you control. Docker Compose runs Traefik, the Nginx frontend and a separate Python backend. Traefik handles public HTTP/HTTPS, obtains a Let's Encrypt certificate and routes requests; only ports 80 and 443 are published. The frontend and backend remain private on the Compose network.

This is a **test environment** with its own database and keys. The bundle does not include local databases, secrets or certificates. SMTP/email delivery is not configured.

## 1. Prepare the VPS and DNS

Create a DNS A record for the test hostname pointing to the VPS. Add an AAAA record only if IPv6 works on that VPS. Allow SSH and TCP ports 80 and 443 through the provider's firewall. The hostname must resolve publicly and port 80 must be reachable for the Let's Encrypt HTTP challenge.

Connect to the VPS and set the hostname, without `https://` or a trailing slash:

```bash
ssh YOUR_SSH_USER@YOUR_VPS_IP
export TEST_DOMAIN="test.yourdomain.nl"
```

## 2. Install Docker on the VPS

On a fresh Ubuntu installation, install Docker Engine and the Compose plugin using [Docker's Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/). Check that `sudo docker compose version` works. Traefik replaces the previous host Nginx and Certbot setup; these do not need to be installed for a fresh test server.

If another service already uses ports 80 or 443, arrange the switchover before starting Traefik. Do not stop or reconfigure a shared proxy without checking what else it serves.

## 3. Package and upload the test release

On your Windows PC, from the `RitmeRobotTestServer` repository, make sure the complete fetched game export is available in `.godot-export/`, then run:

```powershell
pwsh -NoProfile -File scripts/package-vps-test.ps1
scp "PATH_TO_THE_GENERATED_ARCHIVE.tar.gz" YOUR_SSH_USER@YOUR_VPS_IP:~/ritmerobot-test.tar.gz
```

The script prints the archive path. It builds the frontend and packages the tracked backend source without local secrets, certificates or databases. Set `GODOT_EXPORT_DIR` if the export is elsewhere. Use `-SkipBuild` to package an existing complete `dist/`.

On the VPS, unpack a fresh installation:

```bash
sudo install -d -m 0755 -o "$(id -un)" -g "$(id -gn)" /opt/ritmerobot-test
tar -xzf ~/ritmerobot-test.tar.gz -C /opt/ritmerobot-test
cd /opt/ritmerobot-test
```

## 4. Configure Traefik and start the services

Create the Compose environment file without replacing an existing one, then edit `.env` to set `ACME_EMAIL` to your real Let's Encrypt contact email:

```bash
cp -n .env.example .env
bash scripts/configure-traefik.sh "$TEST_DOMAIN"
sudo docker compose build
sudo bash scripts/generate-secrets.sh
sudo docker compose up -d
sudo docker compose ps
```

The Traefik setup script validates the hostname and generates `traefik/routes.yml`; it refuses to overwrite an existing route file. The key generator also refuses to replace an existing nonempty `backend.env`. The backend loads that file through python-dotenv; do not pass it as Docker's `--env-file` because quoted signing-key newline escapes would be handled differently.

Traefik stores its certificate account and keys in the `traefik-certificates` Docker volume. Preserve this volume along with `backend.env` and `data/`: replacing the backend encryption key makes existing organization email data unreadable. `docker compose down` keeps the volume; do not add `-v` if the data must be retained.

Wait for the backend health response to include `"status":"ok"` and `"database":"connected"`:

```bash
sudo docker compose exec -T backend python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/api/health").read().decode())'
curl -I "https://$TEST_DOMAIN/"
```

Certificate issuance can take a little time. If startup or HTTPS fails, inspect `sudo docker compose logs --tail=80 traefik backend frontend`, DNS and the firewall. Do not share `backend.env` or certificate data. The HTTPS response should include `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`.

## 5. Create a test staff account and license

From `/opt/ritmerobot-test`:

```bash
read -rsp "New test admin password: " TEST_ADMIN_PASSWORD
printf '\n'
sudo docker compose exec -T backend python main.py add_user rene "$TEST_ADMIN_PASSWORD"
unset TEST_ADMIN_PASSWORD
```

Look for `User 'rene' added successfully`; the backend command can log an error even when its exit status is zero. Open `https://YOUR_TEST_HOSTNAME/admin/login`, sign in, then create a test organization and a license with a future expiry date.

Open `https://YOUR_TEST_HOSTNAME/` in a private browser window, enter the license code and choose **Spelen**. Player and staff logins share a cookie, so use separate browser profiles or a private window to keep both sessions.

Traefik routes ordinary `/api/` requests directly to the backend. Login and license verification pass through the frontend's internal Nginx so stale cookies are cleared and the backend's `access_token` receives `Secure` and `HttpOnly`. Nginx also checks the session with the backend before serving protected WASM, PCK and Godot engine/worklet files. This controls server downloads, not files already downloaded or cached on a device.

## 6. Verify

- HTTPS opens without a certificate warning, and HTTP redirects to HTTPS.
- Unknown licenses are rejected; an expired cookie does not prevent a new login.
- The `access_token` cookie has `Secure` and `HttpOnly` flags.
- In a private session, direct PCK/WASM requests are denied before login and work after login.
- `/admin/login` and deeper admin links work; missing assets return real 404 responses.
- The real game, soundfont/audio workers, microphone and performance work on the target device.
- Restarting services preserves users and licenses: `sudo docker compose restart`.

## Updating and stopping

Generate a new archive from the `RitmeRobotTestServer` repository with `pwsh -NoProfile -File scripts/package-vps-test.ps1`. Upload and unpack it into a **fresh staging directory** on the VPS. Compare and update the application files in `/opt/ritmerobot-test`, replacing the complete `frontend/dist/` directory so old game files do not remain. Review changes to the Traefik route template and merge them into your generated `traefik/routes.yml` if necessary. Do not overwrite the existing `.env`, `backend.env`, `data/`, route file or certificate volume.

From `/opt/ritmerobot-test`, rebuild and recreate with `sudo docker compose up -d --build`. For a frontend-only update, use `sudo docker compose up -d --build frontend`. An open player may need to reload after an update.

Stop the test containers with `sudo docker compose down`. Keep `.env`, `backend.env`, `data/`, `traefik/routes.yml` and the certificate volume for the next run.
