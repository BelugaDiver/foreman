# Quickstart: Completion Test UI

**Phase**: 1 (Design)  
**Date**: 2026-05-13  
**Audience**: Developers setting up or contributing to the completion test UI

## 5-Minute Setup

### Prerequisites
- Foreman service running on `http://localhost:8000` (or Docker Compose setup)
- Python 3.7+ (for serving static files)
- Modern web browser (Chrome, Firefox, Safari, Edge)
- **Storage bucket CORS configured**: The S3/R2 bucket must allow PUT from `http://localhost:3000`. Without this, image uploads will be blocked by the browser. See your bucket's CORS settings.

### Steps

1. **Start foreman backend** (if not already running):
   ```bash
   cd /path/to/foreman
   docker-compose up foreman  # or: python -m foreman.main
   ```
   Verify: Open `http://localhost:8000/health` in browser; should see health check response

2. **Navigate to UI directory**:
   ```bash
   cd foreman/ui
   ```

3. **Start simple HTTP server**:
   ```bash
   python -m http.server 3000
   ```
   Output:
   ```
   Serving HTTP on port 3000 (http://0.0.0.0:3000/)
   ```

4. **Open in browser**:
   ```
   http://localhost:3000
   ```

5. **Create a test user**:
   - Click "Create User" button on startup screen
   - Enter email and name (e.g., `dev@example.com`, `Dev User`)
   - Click "Create"
   - UI auto-discovers foreman at `http://localhost:8000` and sets x-user-id header

6. **Create a project**:
   - Click "New Project" button
   - Enter project name (e.g., "My Test Project")
   - Click "Create"

7. **Upload a test image** *(required before first generation)*:
   - With the project selected, click "Upload Image"
   - Pick a local image file (JPEG, PNG, WebP, or GIF)
   - UI requests a presigned URL from foreman, then uploads directly to storage
   - On success, the project's input image is set automatically
   - You should see the image thumbnail in the project view

8. **Submit a generation job**:
   - Click "New Generation" button
   - Enter prompt (e.g., "Modern minimalist interior design")
   - Optionally select a style from dropdown
   - Click "Submit"
   - UI shows job details with status "pending"

9. **Monitor completion**:
   - Watch as job status transitions from "pending" → "processing" → "completed"
   - When completed, output image URL is displayed and image is rendered
   - Processing time is shown

**Done!** You've tested the full E2E workflow.

---

## API Discovery Behavior

The UI attempts to find foreman in this order:

1. **Check localhost:8000 first** (most common dev setup)
   - Sends `GET http://localhost:8000/health`
   - If successful (200 response), uses `http://localhost:8000` as API base

2. **Fallback: Dynamic discovery** (if localhost:8000 fails)
   - Tries `GET /.well-known/openapi.json` (relative to current origin)
   - Or `GET http://current-origin/foreman-api` (configurable)
   - Looks for foreman service registration

3. **Manual override** (if auto-discovery fails)
   - Click "Settings" gear icon
   - Enter foreman API URL manually (e.g., `http://staging-foreman:8000`)
   - Click "Save"

---

## Key UI Views

### Settings Panel
- **x-user-id**: Manual entry for existing users (default: from user creation)
- **API Base URL**: Override foreman endpoint (default: `http://localhost:8000`)
- **Polling Interval**: Adjust how often job status is checked (default: 3 seconds)

### Projects View
- List all projects for current user
- Create new project
- Select project to see its generations

### Generation Form
- **Prompt** (required): Text describing the image to generate
- **Style** (optional): Design style from dropdown
- **Parent Generation** (optional): For chained generations
- Submit button creates job on foreman; navigates to job detail view

### Job List View
- Shows all generations in selected project (paginated)
- Click generation to view details
- Filter by status (pending, processing, completed, failed)

### Job Detail View
- **Status**: Current state (pending/processing/completed/failed/cancelled)
- **Prompt**: Original prompt text
- **Input Image**: Link to input image URL
- **Output Image**: Rendered output image (if completed)
- **Processing Time**: How long job took (if completed)
- **Error Message**: If job failed
- **Actions**:
  - **Refresh**: Fetch latest status manually
  - **Cancel**: Stop if pending/processing
  - **Retry**: Create new job with same inputs (if failed)
  - **Fork**: Create child job using output as input (if completed)

---

## Browser Behavior & Gotchas

### localStorage Persistence
- User ID and API URL persist in localStorage
- Survive page refresh, but not incognito/private mode
- Clear via browser dev tools if needed: `localStorage.clear()`

### Polling & Background Tabs
- Polling pauses if tab is backgrounded (to save resources)
- Resumes when tab comes back to focus
- Can still manually refresh in background tab

### CORS & Same-Origin Policy
- If foreman API is on different origin, may need CORS headers
- Default setup (UI at localhost:3000, API at localhost:8000) works fine
- For staging/production, foreman must include `Access-Control-Allow-Origin` header

### Image Display
- Output images must be accessible from browser (public URL or signed URL)
- If image fails to load, click URL to verify it's valid in separate tab

---

## Common Workflows

### Testing Job Creation
1. Create project
2. Upload a test image (required — sets `original_image_url` on the project)
3. Fill form: prompt="test prompt", style=any
4. Submit
5. Verify job appears with status="pending"

### Testing Image Upload
1. Create a project
2. Click "Upload Image" → pick a .jpg or .png file
3. Verify progress bar reaches 100%
4. Verify project now shows uploaded image thumbnail
5. Verify `original_image_url` is set on the project (visible in project detail)
6. Now submit a generation — it should use the uploaded image as input

### Testing Job Completion
1. Submit generation job (ensure worker is running)
2. Wait or refresh (polling auto-updates every 3 seconds)
3. When complete, verify output image renders

### Testing Job Chains
1. Complete a generation
2. Click "Fork" on completed job
3. Enter new prompt
4. Submit forked generation
5. Verify parent_id set correctly on new job

### Testing Error Handling
1. Try creating generation with empty prompt → validation error displayed
2. Try using wrong x-user-id → 422 error shown
3. Stop foreman → network error toast shown
4. Restart foreman → UI recovers on next action

---

## Development Tips

### Debugging
- **Browser Console** (`F12`): Logs API calls, errors, state changes
- **Network Tab**: Monitor API requests; see response bodies
- **Application / Storage**: Inspect localStorage values
- **Search for "DEBUG"**: Code has console.log statements prefixed with "DEBUG"

### Modifying UI
- Edit `foreman/ui/components/*.js` files
- No build step needed; just refresh browser
- CSS changes in `foreman/ui/styles.css` apply immediately

### Testing Without Real Worker
- Jobs will stay in "pending" state indefinitely
- Manually update generation status via foreman admin panel (if available)
- Or configure worker to use mock/test mode

### Performance
- Polling every 3 seconds is default; adjust in settings
- Faster polling = more API calls; slower polling = higher latency
- UI should remain responsive even with many old jobs in list

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Image upload fails with CORS error | S3/R2 bucket missing CORS config | Add PUT CORS rule for `http://localhost:3000` on the bucket |
| Image upload fails with 403 from storage | Presigned URL expired | Click upload again; UI auto-requests fresh presigned URL |
| "Project has no input image" warning on generation form | `original_image_url` not set | Upload an image first; project is updated automatically |
| Upload progress stalls at 0% | Network blocked or storage unreachable | Check browser console for CORS/network errors |
| Image thumbnail doesn't render after upload | Signed URL expired | Re-fetch image list; URLs are short-lived |
| Image upload fails with 422 | Invalid content_type or size_bytes=0 | Use JPEG/PNG/WebP/GIF; ensure file size > 0 bytes |
| "Failed to connect to API" on startup | Foreman not running | Start foreman; verify `http://localhost:8000/health` responds |
| Settings don't persist after page refresh | localStorage disabled | Enable cookies/storage in browser settings |
| Job status doesn't update | Polling stopped | Check if tab is backgrounded; click refresh manually |
| Output image doesn't show | Image URL invalid/inaccessible | Click URL to test in separate tab; check worker uploaded correctly |
| Validation error on form submit | Missing required field | Ensure prompt is filled; at least 1 character |
| 422 error on user creation | Invalid email format | Use valid email (e.g., `test@example.com`) |
| x-user-id not being set | User creation failed | Check browser console for errors; verify x-user-id in localStorage |

---

## API Endpoints Referenced

See [contracts/api-endpoints.md](../contracts/api-endpoints.md) for full API documentation.

**Summary of endpoints used**:
- `GET /health` — Discovery
- `POST /v1/users/` — User creation
- `GET /v1/users/me` — Get current user
- `GET/POST /v1/projects/` — Project list + create
- `PATCH /v1/projects/{id}` — Set original_image_url after upload
- `POST /v1/projects/{id}/images` — Upload intent (get presigned URL)
- `GET /v1/projects/{id}/images` — List uploaded images
- `GET /v1/images/{id}` — Get signed download URL post-upload
- `PUT {presigned_url}` — Direct upload to S3/R2 (not a foreman endpoint)
- `GET /v1/styles/` — Style options
- `POST /v1/projects/{id}/generations` — Create job
- `GET /v1/generations/{id}` — Get job status
- `GET /v1/projects/{id}/generations` — List jobs
- `POST /v1/generations/{id}/cancel` — Cancel job
- `POST /v1/generations/{id}/retry` — Retry failed job
- `POST /v1/generations/{id}/fork` — Fork completed job

---

## Next Steps

- **Contribute**: Add features or fixes; see CONTRIBUTING.md
- **Report Issues**: File bugs in GitHub Issues
