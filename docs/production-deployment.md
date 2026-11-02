# Production server integration

This guide describes the full-server integration. Unless noted otherwise, paths and commands below are relative to the separate `ritmerobot-frontend` repository.

Traefik terminates HTTPS and routes public requests. It sends `/api/` to the existing backend and the frontend hostname's other requests to the frontend container. Nginx inside that container serves the built React and Godot files and handles frontend routes. For protected game downloads, Nginx also makes a private session check against the backend.

The backend already runs separately in Docker. Keep its existing container, database and secrets. The frontend Compose file manages only the frontend. Previous frontend deployment files are in `ritmerobot-frontend/archive/`.

## Build the frontend

The Docker build requires a complete Godot web export and the `player-shell.html` template from the Godot source repository. Configure `GODOT_EXPORT_DIR` to point to the fetched export directory and `GODOT_SHELL_DIR` to the directory containing the template. Set `GODOT_ENTRY_FILE` if the exported HTML is not named `ritme_robot.html`. The export must include all matching WASM, PCK, audio worklets and extensions, including actual Git LFS files. The build validates these inputs but does not fetch or export the game; the server's game-file source still needs to be set up.

From the frontend repository root, after fetching the files:

```sh
cp -n .env.example .env
# Edit .env: provide the export, template and server settings.
docker compose build frontend
```

The multi-stage Dockerfile builds the frontend and places the player shell, `/admin/` bundle, `/play/` assets, manifest and service workers in the Nginx image. Docker Compose with a BuildKit builder supporting named contexts is required. When migrating an existing installed PWA, preserve its actual app identity using `PWA_APP_ID` before building. The default is `/godot/ritme_robot.html`.

## Connect the frontend to the server

In the frontend repository's `.env`, set:

- `BACKEND_UPSTREAM`: the backend hostname and port reachable from the frontend container for its internal `GET /api/auth/validate` session check. The default `backend:8000` works only when that hostname is available on a shared Docker network. Do not use `localhost` unless the backend really runs inside the frontend container.
- `FRONTEND_PORT`: the host port to publish; it defaults to 5173.

The frontend's root `docker-compose.yml` publishes port 5173 and does not configure the server's router. Configure the existing Traefik setup to forward the frontend hostname to that published port and to handle HTTPS. If Traefik runs in a container, use a host address or network connection it can actually reach. If frontend and backend run in separate Compose projects, make the backend reachable from the frontend container through an existing shared network or another private address. Publishing the frontend port makes it reachable according to the host firewall and network configuration.

The **existing backend router** must match the same public hostname and `/api/`, route to the backend and take precedence over the frontend route. Do not strip the `/api` prefix. The frontend Nginx returns 404 for `/api/`, so accessing its published port directly does not provide the API.

The previous host Nginx removed an expired session cookie on `/api/auth/login` and `/api/auth/verify` so a new login could replace it. Because Traefik now handles these requests, preserve that behavior in Traefik: configure a higher-priority router for those two exact paths with a headers middleware that removes the request `Cookie` header, and send it to the existing backend service. For example, adapt these Docker labels on the **backend** service to its actual hostname, Traefik service and entrypoint:

```yaml
labels:
  traefik.http.routers.ritmerobot-auth.rule: "Host(`ritmerobot.example`) && (Path(`/api/auth/login`) || Path(`/api/auth/verify`))"
  traefik.http.routers.ritmerobot-auth.entrypoints: websecure
  traefik.http.routers.ritmerobot-auth.tls: "true"
  traefik.http.routers.ritmerobot-auth.priority: "1000"
  traefik.http.routers.ritmerobot-auth.service: YOUR_EXISTING_BACKEND_SERVICE
  traefik.http.routers.ritmerobot-auth.middlewares: ritmerobot-clear-login-cookie
  traefik.http.middlewares.ritmerobot-clear-login-cookie.headers.customrequestheaders.Cookie: ""
```

The auth router must outrank both the normal API router and the frontend router. Apply the cookie-removal middleware **only** to login and verify; session validation and other API requests need their cookies. The previous host proxy also added `Secure` and `HttpOnly` flags to the `access_token` cookie. The current backend sets `HttpOnly`, but its login and license responses do not set `Secure`; configure the backend or an appropriate Traefik-compatible response middleware to add `Secure` before production use. HTTPS termination alone does not add that flag.

## Build and start the frontend container

From the repository root on the Linux host with Docker available:

```sh
docker compose build frontend
docker compose up -d frontend
docker compose ps frontend
```

The root `dockerfile` compiles the frontend in a Node build stage and serves the resulting files from Nginx. The default image is `ritmerobot-frontend:production`; `FRONTEND_IMAGE` overrides it. The server's existing deployment tool is responsible for triggering the build and switching over the frontend. This repository does not configure that tool or modify the backend.

## Frontend routing and protection

Nginx serves `/` and the player assets, serves React Admin and its client-side routes under `/admin/`, and returns real 404 responses for missing files. It supplies the COOP/COEP headers needed by Godot, the correct WASM and web-manifest content types, and the service-worker migration routes. Traefik handles public TLS and API routing.

For matching WASM, PCK and Godot engine/worklet JavaScript under `/play/`, Nginx sends the session cookie directly to the backend's validation endpoint. The backend accepts authenticated player or staff sessions. An invalid session is denied; an unavailable backend prevents the protected download. The JavaScript rule assumes the Godot executable is named `ritme_robot`; adjust it if the fetched export uses another name. Keep the backend and frontend reachable only through the intended proxy/network paths: direct access to the static files would bypass the session check. This controls server downloads; files already downloaded or cached can still be copied.

The player and staff share the backend's `access_token` cookie; a new login replaces the existing session. Player access requires an online session check even when the PWA shell is cached. There is no backend logout endpoint. The service worker caches a copy of the player shell and can cache game files. A new image replaces the complete release; an open player may need to reload. Preserve Godot extension filenames and basenames in the export.

## Verify

- Confirm Traefik routes `/api/` to the backend and `/`, `/admin/` and `/play/` to the frontend on the same HTTPS origin, with a valid certificate.
- Check that an expired cookie does not prevent a new login and that the returned `access_token` has `Secure` and `HttpOnly` flags.
- In a private session, check that an unknown license is rejected and a direct request for the current PCK or WASM is denied before login and succeeds after login.
- Open `/admin/login` and a deeper admin link directly; check COOP/COEP headers, WASM content type, real 404s and the PWA update flow.
- Check audio, microphone/MIDI and performance on the target device. A build or container health check does not verify these.

For local Nginx routing checks, install Nginx and run `python3 tests/production-nginx.py` from the repository root. `NGINX_BIN` and `NGINX_MIME_TYPES` can point to a nonstandard executable and MIME file. These tests use a local backend fixture; they do not test the deployed Traefik configuration or the real backend.
