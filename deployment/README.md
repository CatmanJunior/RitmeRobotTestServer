# Install the RitmeRobot test server from scratch

This test bundle targets a fresh Ubuntu 24.04 LTS VPS and a test hostname you control. Docker Compose runs Traefik, the Nginx frontend and a separate Python backend. Traefik handles public HTTP/HTTPS, obtains a Let's Encrypt certificate and routes requests; only ports 80 and 443 are published. The frontend and backend remain private on the Compose network.

This is a **test environment** with its own database and keys. The bundle does not include local databases, secrets or certificates. SMTP/email delivery is not configured.

The steps below use two machines: a Windows PC to prepare the release and a fresh Ubuntu VPS to run it. Commands are labelled by machine. If you already have a compatible test-release archive, skip the Windows preparation and use that archive in step 4.

You need:

- A fresh Ubuntu 24.04 LTS VPS with a public IP address, internet access and an SSH user with `sudo` access.
- A test hostname you can configure in DNS, and access to the VPS provider's firewall. This guide uses `test.yourdomain.nl` as an example.
- To build an archive: access to the test-server, frontend, backend and Godot source repositories, and a complete Godot web export or the means to create one.
- To build an archive: a Windows packaging PC with [PowerShell 7](https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-windows), [Git](https://git-scm.com/install/windows), [Node.js](https://nodejs.org/en/download) 22.12 or newer with npm, `tar.exe`, and an SSH client with `scp`. Docker and Python are not needed on this PC for packaging. Use Git LFS if any of the source files or supplied export are stored in LFS.

The deployment files and the three source repositories must be compatible versions of the same release. The example commands contain placeholders such as `YOUR_VPS_IP`; replace them with your own values. Do not enter the angle brackets shown in the directory tree as part of a command.

## 1. Prepare the release on Windows

Open PowerShell 7. Check the tools with `pwsh --version`, `git --version`, `node --version`, `npm --version`, `tar.exe --version` and `Get-Command scp`. Install missing tools and reopen PowerShell so they are on the PATH.

Check out the four repositories in this layout. The root can be anywhere; the relative paths and directory names matter to the packaging script:

```text
<workspace>/
  frontend/
    RitmeRobotTestServer/
    ritmerobot-frontend/
  backend/
    ritmerobot-backend/
  youbeatai-godot-web/
```

For example, replace the four quoted repository URL placeholders below with the URLs supplied by your project administrator and run:

```powershell
$taskRoot = 'C:\RitmeRobot'
New-Item -ItemType Directory -Force -Path "$taskRoot\frontend", "$taskRoot\backend" | Out-Null
git clone 'YOUR_TEST_SERVER_REPOSITORY_URL' "$taskRoot\frontend\RitmeRobotTestServer"
git clone 'YOUR_FRONTEND_REPOSITORY_URL' "$taskRoot\frontend\ritmerobot-frontend"
git clone 'YOUR_BACKEND_REPOSITORY_URL' "$taskRoot\backend\ritmerobot-backend"
git clone 'YOUR_GODOT_REPOSITORY_URL' "$taskRoot\youbeatai-godot-web"
```

Select the intended release or branches in each checkout. If a repository uses Git LFS, install Git LFS, run `git lfs install`, then run `git lfs pull` in that repository. A Git LFS pointer is not the actual game asset.

Obtain the **complete web export** for that release and put its files directly in `frontend/RitmeRobotTestServer/.godot-export/`. The default container build expects the entry file `ritme_robot.html` and matching export files, including the `.pck`, `.wasm`, JavaScript, audio worklets, manifest, icons and any extension files. Keep the exported names and directory structure together. The project does not define how to fetch an existing export, so obtain it from the release provider or create one as described below.

To create an export locally instead, install [Godot 4.6 Standard and the matching export templates](https://godotengine.org/download/archive/4.6-stable/); install the templates from the Godot editor. Make sure the Godot checkout's `Web` export preset and any required native extension files are present. From the test-server repository in PowerShell 7, with an empty `.godot-export` directory:

```powershell
cd "$taskRoot\frontend\RitmeRobotTestServer"
$env:GODOT_BIN = 'C:\PATH\TO\YOUR\GODOT_4.6_STANDARD.exe'
& $env:GODOT_BIN --headless --editor --path ..\..\youbeatai-godot-web --quit
if ($LASTEXITCODE -ne 0) { throw 'Godot import failed; inspect its output.' }
pwsh -NoProfile -File .\scripts\export-game.ps1
```

Inspect the import output for errors even if the exit code is zero. The helper writes export logs under `work/`; it validates the generated files but a successful export does not prove the game works in a browser. See [Godot's export instructions](https://docs.godotengine.org/en/4.6/tutorials/export/exporting_projects.html) if the matching export templates are missing.

Install the frontend dependencies once on the Windows PC:

```powershell
cd "$taskRoot\frontend\ritmerobot-frontend"
npm ci
cd "$taskRoot\frontend\RitmeRobotTestServer"
```

The packaging script uses tracked frontend and backend files from the working tree, including local edits to tracked files, but does not include untracked files. Make sure the intended release files are tracked and that local changes are deliberate. It also needs `youbeatai-godot-web/web/player-shell.html` and the export described above.

## 2. Prepare the VPS and DNS

Create a DNS A record for the test hostname pointing to the VPS. Add an AAAA record only if IPv6 works on that VPS. Allow SSH and TCP ports 80 and 443 through the provider's firewall and, if enabled, the VPS firewall; keep SSH access available. The hostname must resolve publicly and port 80 must be reachable for the Let's Encrypt HTTP challenge.

Connect from the packaging PC with `ssh YOUR_SSH_USER@YOUR_VPS_IP`. In the resulting VPS shell, enter your real hostname when prompted, without `https://` or a trailing slash. For example, enter `test.example.com` only if that is actually your hostname:

```bash
read -r -p "Your test hostname: " TEST_DOMAIN
export TEST_DOMAIN
```

## 3. Install Docker on the VPS

On the Ubuntu VPS, install Docker Engine, Buildx and the Compose plugin using [Docker's Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/). For a clean Ubuntu 24.04 installation, the official repository method is:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
sudo docker buildx version
```

Follow the official instructions for conflicting pre-existing Docker packages or another Ubuntu release. Traefik handles HTTPS; host Nginx and Certbot do not need to be installed for a fresh test server.

If another service already uses ports 80 or 443, arrange the switchover before starting Traefik. Do not stop or reconfigure a shared proxy without checking what else it serves.

## 4. Package and upload the test release

If you already have a compatible test-release archive, skip the packaging command and upload that archive below. Otherwise, on your Windows PC, from the `RitmeRobotTestServer` repository prepared in step 1, run:

```powershell
pwsh -NoProfile -File .\scripts\package-vps-test.ps1
```

The script validates a frontend build and prints the archive path under `work/`. The archive contains the tracked frontend and backend sources, the complete game export and player shell; it does not contain local secrets, certificates or databases. Docker Compose builds the frontend and backend using the Dockerfiles and Nginx configuration from their respective repositories. Set `GODOT_EXPORT_DIR` if the export is elsewhere or `GODOT_SHELL_PATH` if the shell template is elsewhere; relative paths are resolved from the frontend repository. Use `-SkipBuild` only when an already validated `dist/play/build-version.txt` exists; it skips local validation.

Replace the path below with the exact `Upload this archive` path printed by the script (or the path to your existing archive), and replace the SSH user and IP address:

```powershell
scp 'C:\PATH\TO\ritmerobot-vps-test-TIMESTAMP.tar.gz' YOUR_SSH_USER@YOUR_VPS_IP:~/ritmerobot-test.tar.gz
```

On the VPS, unpack a fresh installation. These commands assume `/opt/ritmerobot-test` does not already contain another installation:

```bash
sudo install -d -m 0755 -o "$(id -un)" -g "$(id -gn)" /opt/ritmerobot-test
tar -xzf ~/ritmerobot-test.tar.gz -C /opt/ritmerobot-test
cd /opt/ritmerobot-test
```

## 5. Configure Traefik and start the services

On the VPS, still in `/opt/ritmerobot-test`, create the Compose environment file without replacing an existing one:

```bash
cp -n .env.example .env
nano .env
```

Set `ACME_EMAIL` to your real Let's Encrypt contact email and save the file. Then run the following. If you reconnected to SSH since step 2, set `TEST_DOMAIN` again first.

```bash
bash scripts/configure-traefik.sh "$TEST_DOMAIN"
grep -F 'Host(' traefik/routes.yml
sudo docker compose config --quiet
sudo docker compose build
sudo bash scripts/generate-secrets.sh
sudo docker compose up -d
sudo docker compose ps
```

The Traefik setup script validates the hostname and generates `traefik/routes.yml`; it refuses to overwrite an existing route file. Check that every hostname printed by `grep` is your real test hostname. Changing `TEST_DOMAIN` later does not change the generated routes. If the file has the wrong hostname, edit all three `Host(...)` rules in `traefik/routes.yml`, then recreate Traefik with `sudo docker compose up -d --no-deps --force-recreate traefik`. The key generator also refuses to replace an existing nonempty `backend.env`. The backend loads that file through python-dotenv; do not pass it as Docker's `--env-file` because quoted signing-key newline escapes would be handled differently.

Traefik stores its certificate account and keys in the `traefik-certificates` Docker volume. Preserve this volume along with `backend.env` and `data/`: replacing the backend encryption key makes existing organization email data unreadable. `docker compose down` keeps the volume; do not add `-v` if the data must be retained.

Wait for the backend health response to include `"status":"ok"` and `"database":"connected"`:

```bash
sudo docker compose exec -T backend python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/api/health").read().decode())'
curl -I "https://$TEST_DOMAIN/"
```

Certificate issuance can take a little time. If startup or HTTPS fails, inspect `sudo docker compose logs --tail=80 traefik backend frontend`, DNS and the firewall. Do not share `backend.env` or certificate data. The HTTPS response should include `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`.

## 6. Create a test staff account and license

From `/opt/ritmerobot-test`:

```bash
read -rsp "New test admin password: " TEST_ADMIN_PASSWORD
printf '\n'
sudo docker compose exec -T backend python main.py add_user testadmin "$TEST_ADMIN_PASSWORD"
unset TEST_ADMIN_PASSWORD
```

Look for `User 'testadmin' added successfully`; the backend command can log an error even when its exit status is zero. Open `https://YOUR_TEST_HOSTNAME/admin/login`, sign in with `testadmin` and the password you chose, then create a test organization and a license with a future expiry date. The organization form requires a name and email address; the license form requires the organization and expiry date. Copy the generated license code.

Open `https://YOUR_TEST_HOSTNAME/` in a private browser window, enter the license code and choose **Spelen**. Player and staff logins share a cookie, so use separate browser profiles or a private window to keep both sessions.

Traefik routes ordinary `/api/` requests directly to the backend. Login and license verification pass through the frontend repository's Nginx so stale cookies are cleared and the backend's `access_token` receives `Secure` and `HttpOnly`. Nginx also checks the session with the backend before serving protected WASM, PCK and Godot engine/worklet files. This controls server downloads, not files already downloaded or cached on a device.

## 7. Verify

- HTTPS opens without a certificate warning, and HTTP redirects to HTTPS.
- Unknown licenses are rejected; an expired cookie does not prevent a new login.
- The `access_token` cookie has `Secure` and `HttpOnly` flags.
- In a private session, direct PCK/WASM requests are denied before login and work after login.
- `/admin/login` and deeper admin links work; missing assets return real 404 responses.
- The real game, soundfont/audio workers, microphone and performance work on the target device.
- Restarting services preserves users and licenses: `sudo docker compose restart`.

As an additional check from the VPS, a request without a login should be denied access to the game pack:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://$TEST_DOMAIN/play/ritme_robot.pck"
```

Expect `401` or `403`, not a successful download. In the browser, repeat the check after a valid login and confirm that the game loads. These checks do not prevent copying game files already downloaded or cached on a device.

## Preserve test data and keys

The live database is `data/db.sqlite3` on the VPS. Keep the whole `data/` directory and `backend.env` together in a protected backup; the encryption key in `backend.env` is needed to read encrypted organization email data. Take an application-consistent SQLite backup, or stop the backend before copying the whole `data/` directory, and test restoration separately. Preserve `.env`, `traefik/routes.yml` and the Traefik certificate volume as well.

**Current limitation:** the backend's scheduled and manual backup/restore code defaults to `db.sqlite3` in the application directory, while the running application uses `data/db.sqlite3`. Until those paths are corrected and verified, do not rely on the built-in backup or restore functions to protect the live database.

## Updating and stopping

Generate a new archive from the `RitmeRobotTestServer` repository with `pwsh -NoProfile -File scripts/package-vps-test.ps1`. Upload and unpack it into a **fresh staging directory** on the VPS. Compare and update the complete `frontend/`, `backend/`, `game-export/` and `game-shell/` build inputs in `/opt/ritmerobot-test`. Review changes to the Traefik route template and merge them into your generated `traefik/routes.yml` if necessary. Do not overwrite the existing `.env`, `backend.env`, `data/`, route file or certificate volume.

From `/opt/ritmerobot-test`, rebuild and recreate with `sudo docker compose up -d --build`. For a frontend-only update, use `sudo docker compose up -d --build frontend`. An open player may need to reload after an update.

Stop the test containers with `sudo docker compose down`. Keep `.env`, `backend.env`, `data/`, `traefik/routes.yml` and the certificate volume for the next run.
