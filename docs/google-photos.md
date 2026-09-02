# Google Photos access

Publishing uses the [Google Photos Library API](https://developers.google.com/photos). Sign-in happens in the **browser UI** (a Google popup), not in a backend terminal.

You need a **Web application** OAuth client (not Desktop / installed). The UI requests Photos scopes; the backend only receives a short-lived access token for that publish job. Tokens are stored in the **browser** only (not on the server / job store).

Preview and web import do not need this setup.

## 1. Enable the API

In [Google Cloud Console](https://console.cloud.google.com/), create or pick a project and enable the [Photos Library API](https://console.cloud.google.com/apis/library/photoslibrary.googleapis.com).

## 2. Consent screen

Configure the OAuth consent screen (External, Testing is fine).

Add the Google account you will sign in with as a **test user**. Without that, Testing mode will refuse the popup.

Scopes this app requests:

- `https://www.googleapis.com/auth/photoslibrary`
- `https://www.googleapis.com/auth/photoslibrary.appendonly`
- `https://www.googleapis.com/auth/photoslibrary.sharing`
- `https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata`

## 3. Web OAuth client

Create an OAuth client of type **Web application**.

**Authorized JavaScript origins:**

- `http://localhost:5173`
- `http://127.0.0.1:5173`

**Authorized redirect URIs** (same origins are enough for the popup sign-in):

- `http://localhost:5173`
- `http://127.0.0.1:5173`

Download the JSON. Rename it **`client_secrets.json`**.

## 4. Where to put the file

| How you run | Put the file here |
|-------------|-------------------|
| Docker Compose | Repository **root** (`./client_secrets.json`), so the backend volume mount works |
| Host uvicorn | `services/backend/client_secrets.json` (process CWD) |

You may keep both copies. Both are gitignored (`*client_secret*`). **Do not commit this file.**

## 5. Environment variables (Cloud Run)

Local and Compose keep using the file. On Cloud Run there is no mounted `client_secrets.json` — set env (or Secret Manager → env). Blank / whitespace-only env is treated as **absent** and falls back to the file.

| Env | Meaning |
|-----|---------|
| `GOOGLE_OAUTH_CLIENT_ID` | Web OAuth **client id** only. Highest precedence when non-empty. |
| `GOOGLE_OAUTH_CLIENT_SECRETS` | Full `client_secrets.json` text (`web` / `installed` → `client_id`). |
| `GOOGLE_CLIENT_SECRETS_JSON` | Alias for the same JSON text (use either). |
| `GOOGLE_CLIENT_SECRETS` | **Path** to a secrets file (not JSON content). Default: `./client_secrets.json`. |

**Precedence** (first non-empty wins):

1. `GOOGLE_OAUTH_CLIENT_ID`
2. JSON in `GOOGLE_OAUTH_CLIENT_SECRETS` or `GOOGLE_CLIENT_SECRETS_JSON`
3. File at `GOOGLE_CLIENT_SECRETS` or `./client_secrets.json`

The UI loads config from `GET /api/auth/config` (`client_id` + scopes only). The backend never returns or logs `client_secret`. If neither env nor file yields a client id, that endpoint returns **503** and Publish cannot start.

## 6. Publish in the UI

1. Finish a preview and click **Publish** (or check **Auto-publish** when starting an import).
2. The first time, Google’s popup asks you to sign in and allow Photos access. Later publishes reuse that browser session until the token expires (or Google returns 401).
3. The app sends the access token with the publish request. A **new upload job** starts; the preview job stays as-is.
4. When the upload finishes, open the Google Photos album link.

If the popup is closed or denied, sign-in is cancelled and nothing is uploaded. Use **Settings → Sign out of Google Photos** to clear the saved browser session.

## What Google Photos receives

- An album titled like your gallery
- Journal (when present): heading as a short centered text block, then paragraphs
- Optional gallery description (below the journal if both exist)
- Photo / video titles
- Items in gallery order
- Capture times stamped before upload (JPEG EXIF + file times) so Photos sorts by the trip date. See [Album layout](album-layout.md#dates).

Each **Publish** / **Publish again** creates a new independent Photos album. Overwriting a stored preview on this server does **not** change or republish Google Photos.

## Next

- [Using the app](using-the-app.md)
- [Getting started](getting-started.md)
