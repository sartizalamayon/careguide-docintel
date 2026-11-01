# Free deployment

DocIntel runs on three free services with no credit card:

| Part | Host | Free tier used |
|---|---|---|
| Web app (Next.js) | Vercel Hobby | No sleep. Request bodies up to 4.5 MB, so uploads are capped at 4 MB |
| API + document worker | Render free web service | 512 MB, sleeps after 15 min idle (about 1 min to wake) |
| Database | Neon free | 1 GB Postgres with pgvector, pauses after 5 min idle (wakes in about a second) |

The full Docker setup (`docker compose up`) needs about 1 GB of memory and a separate worker and Redis. On the free API host the same code runs in a small-host mode, set in `render.yaml`:

| Setting | Effect |
|---|---|
| `WORKER_MODE=inline` | Jobs run in a background thread of the API process, one at a time, with the same retry policy as the Celery task. No Redis. Unfinished jobs are queued again when the service wakes up |
| `STORAGE_BACKEND=database` | Originals are also stored in Postgres (`stored_files`), because the free disk is wiped when the service sleeps. A missing file is written back on first use |
| `EMBEDDING_PROVIDER=api` | Embeddings come from Gemini (`gemini-embedding-2`, 384 dimensions) instead of the local ONNX model, which needs about 200 MB |
| `MALLOC_ARENA_MAX=2`, `OCR_THREADS=1`, `LLM_CONCURRENCY=2` | Lower memory use |

Measured with these settings on a scanned PDF, a photo, a TIFF, a multi-page PDF and a workbook: peak memory 348 MB (536 MB with the default settings, over the 512 MB limit).

## Steps

### 1. Database (Neon)
1. Sign up at https://neon.com with GitHub. Create a project called `docintel` in the region closest to you.
2. On the project dashboard, click **Connect**, turn **Connection pooling off** (the API keeps its own pool and uses prepared statements), and copy the connection string. It starts with `postgresql://`; paste it as it is.

### 2. API (Render)
1. Sign up at https://render.com with GitHub and give it access to this repository.
2. **New → Blueprint**, pick the repository. Render reads `render.yaml` and asks for three values:
   - `DATABASE_URL`: the Neon string
   - `API_KEY`: a long random string (`openssl rand -hex 24`), the same one goes to Vercel
   - `LLM_API_KEY`: the Gemini key
3. **Apply**. The first build takes about 10 minutes. The API is ready when `https://<service>.onrender.com/api/v1/health` answers `{"status":"ok","db":true,"redis":false,"workers":1}`. Migrations run on every start.

### 3. Web app (Vercel)
1. Sign up at https://vercel.com with GitHub. **Add New → Project**, import the repository, set **Root Directory** to `frontend`.
2. Environment variables:

| Name | Value |
|---|---|
| `BACKEND_URL` | `https://<service>.onrender.com/api/v1` |
| `API_KEY` | the same value as on Render |
| `NEXT_PUBLIC_MAX_FILE_MB` | `4` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | from the Google OAuth client |
| `NEXTAUTH_SECRET` | `openssl rand -base64 32` |
| `NEXTAUTH_URL` | the Vercel URL, e.g. `https://docintel.vercel.app` |

3. **Deploy**.

### 4. Google sign-in
In the Google Cloud console, open the OAuth client and add the Vercel URL:
- Authorized JavaScript origins: `https://docintel.vercel.app`
- Authorized redirect URIs: `https://docintel.vercel.app/api/auth/callback/google`

## Limits of the free setup

- The first request after 15 idle minutes waits about a minute while Render starts the API. The web app shows the request as loading in the meantime.
- Uploads are capped at 4 MB per file (Vercel's request limit), so the 1000-page performance file cannot be uploaded here. It runs in the Docker setup.
- One document is processed at a time.
- Render may stop the service while a long job runs if nobody uses the app for 15 minutes; the job restarts when it wakes.
- Neon free storage is 1 GB for the data and the stored originals together.
