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

- [`deployment/`](deployment/) contains the Traefik and test Docker Compose configuration and setup scripts. Compose builds the frontend and backend with the Dockerfiles and Nginx configuration from their own repositories.
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

The script validates a frontend build, then packages the tracked frontend and backend source from their sibling repositories, together with the Godot export and player-shell build inputs. The VPS Compose build uses the repositories' own Dockerfiles and Nginx configuration. Set `GODOT_EXPORT_DIR` if the export is elsewhere; relative paths are resolved from the frontend project. Set `GODOT_SHELL_PATH` if the player-shell template is elsewhere; relative paths are also resolved from the frontend project. To skip local build validation and use an existing `dist/play/build-version.txt`, pass `-SkipBuild`. Follow the [test VPS guide](deployment/README.md) to deploy the archive.

On Windows, run `python tests/package_test.py` and `node --test tests/godot-export-result.test.mjs` to test packaging and export validation. With Bash, Nginx and Python 3 installed, run `python3 tests/traefik-config.py` and `python3 tests/nginx-routing.py`. With Docker available, `python tests/traefik-integration.py` exercises Traefik, the frontend and a mock backend in temporary containers. These tests do not connect to a live server or request a real certificate.
