# RitmeRobot test server

This repository contains the full-server test deployment, its packaging script and server deployment documentation. The frontend and backend remain separate repositories; no database, secrets, game export or built frontend is tracked here.

The default local layout is:

```text
RitmeRobot Active/
  frontend/
    ritmerobot-frontend/
    RitmeRobotTestServer/    # this repository
  backend/
    ritmerobot-backend/
  youbeatai-godot-web/
```

- [`deployment/`](deployment/) contains the Traefik and test Docker Compose configuration, frontend Nginx image and setup scripts.
- [`deployment/README.md`](deployment/README.md) is the full VPS test setup and update guide.
- [`docs/production-deployment.md`](docs/production-deployment.md) describes the existing production server integration with Traefik and the separate frontend and backend.
- `archive/` preserves the previous host Nginx configurations for reference; they are not the current Traefik setup.
- `scripts/package-vps-test.ps1` builds and packages a test release on Windows.
- `scripts/export-game.ps1` is an optional local Godot export helper; normal deployment uses the fetched export.
- `tests/` checks the test-server packaging and Nginx frontend routing.

The local `.godot-export/`, `dist/` and `work/` directories are ignored by Git. Place the complete fetched Godot web export in `.godot-export/`; `dist/` is the built frontend, and `work/` contains generated bundles. Never add production data or secrets to this repository.

From this directory on Windows with PowerShell 7, Node.js 22.12 or newer, npm, Git, tar and the sibling repositories available:

```powershell
pwsh -NoProfile -File scripts/package-vps-test.ps1
```

The script builds the frontend from the sibling repository into this repository's ignored `dist/`, copies the tracked backend source without secrets and prints the test archive path. Set `GODOT_EXPORT_DIR` if the export is elsewhere; relative paths are resolved from the frontend project. To package the existing `dist/` without rebuilding, pass `-SkipBuild`. Follow the [test VPS guide](deployment/README.md) to deploy the archive.

On Windows, run `python tests/package_test.py` and `node --test tests/godot-export-result.test.mjs` to test packaging and export validation. With Bash, Nginx and Python 3 installed, run `python3 tests/traefik-config.py` and `python3 tests/nginx-routing.py`. With Docker available, `python tests/traefik-integration.py` exercises Traefik, the frontend and a mock backend in temporary containers. These tests do not connect to a live server or request a real certificate.
