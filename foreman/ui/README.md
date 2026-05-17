# Foreman Test UI

A minimal, static web interface for end-to-end testing of the foreman image-generation pipeline.

## Quick Start

### Prerequisites

1. **Foreman running** on `http://localhost:8000`
   ```bash
   docker-compose up foreman
   # or
   uvicorn foreman.main:app --reload
   ```
   Verify: `curl http://localhost:8000/health`

2. **Storage bucket CORS** — if testing image uploads, the S3/R2 bucket must allow PUT from `http://localhost:3000`:
   ```json
   {
     "AllowedOrigins": ["http://localhost:3000"],
     "AllowedMethods": ["PUT"],
     "AllowedHeaders": ["Content-Type", "Content-Length"]
   }
   ```
   Without this the browser will block the presigned-URL upload.

### Run the UI

```bash
cd foreman/ui
python -m http.server 3000
```

Open: **http://localhost:3000**

Full setup guide: [`specs/001-completion-test-ui/quickstart.md`](../../specs/001-completion-test-ui/quickstart.md)

---

## Workflow

1. **Auth** — Create a test user (or paste an existing UUID in Settings → x-user-id)
2. **Projects** — Create a project
3. **Upload** — Upload a JPEG/PNG/WebP/GIF (required before first generation)
4. **Generate** — Submit a generation with a prompt and optional style
5. **Detail** — Watch the job poll from `pending` → `processing` → `completed`
6. **Fork** — Click Fork on a completed job to chain its output as input

---

## File Structure

```
foreman/ui/
├── index.html              # SPA shell — all view containers
├── styles.css              # All styles (~500 lines)
├── app.js                  # Init, routing, polling, notifications
├── api.js                  # HTTP client — all 15 foreman endpoints
├── state.js                # Centralised state + localStorage persistence
└── components/
    ├── utils.js            # Formatters, DOM helpers, validators
    ├── settings.js         # API URL, user ID, polling interval
    ├── auth.js             # User creation / login
    ├── projects.js         # Project list and creation
    ├── image-upload.js     # Presigned-URL upload flow
    ├── generation-form.js  # Generation job submission
    ├── job-list.js         # Paginated job history
    └── job-detail.js       # Job status, polling, cancel/retry/fork
```

---

## API Endpoints Used

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | API discovery |
| POST | `/v1/users/` | Create test user |
| GET | `/v1/users/me` | Validate user ID |
| GET | `/v1/projects/` | List projects |
| POST | `/v1/projects/` | Create project |
| GET | `/v1/projects/{id}` | Get project |
| PATCH | `/v1/projects/{id}` | Set `original_image_url` |
| POST | `/v1/projects/{id}/images` | Get presigned upload URL |
| GET | `/v1/projects/{id}/images` | List uploaded images |
| GET | `/v1/images/{id}` | Get signed download URL |
| GET | `/v1/styles/` | List design styles |
| POST | `/v1/projects/{id}/generations` | Create generation job |
| GET | `/v1/generations/{id}` | Poll job status |
| GET | `/v1/projects/{id}/generations` | List all jobs |
| POST | `/v1/generations/{id}/cancel` | Cancel job |
| POST | `/v1/generations/{id}/retry` | Retry failed job |
| POST | `/v1/generations/{id}/fork` | Fork completed job |

Full contract details: [`specs/001-completion-test-ui/contracts/api-endpoints.md`](../../specs/001-completion-test-ui/contracts/api-endpoints.md)
