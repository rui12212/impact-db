# Local Development Guide

## Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/rui12212/impact-db.git
cd impact-db
git checkout feature/create_docker_environment
```

### 2. Setup Environment Variables
```bash
# Copy template
cp .env.local.template .env.local

# Edit with your credentials
nano .env.local
```

**Required values:**
- `OPENAI_API_KEY`
- `NARRATIVE_TELEGRAM_BOT_TOKEN`
- `IMPACT_TELEGRAM_BOT_TOKEN`
- `NOTION_API_KEY`
- All `NOTION_*_DB_ID` values

### 3. Add Google Cloud Credentials
```bash
# Place service account JSON file
mkdir -p credentials
cp /path/to/service-account.json credentials/
```

### 4. Build & Run
```bash
# Build Docker image (only needed once, ~3-5 minutes)
docker compose -f docker-compose.local.yml build

# Start development server
docker compose -f docker-compose.local.yml up

# Or run in background
docker compose -f docker-compose.local.yml up -d
```

### 5. Test
Open Telegram and send a message to your bot!

Logs will show:
```
INFO: Starting Telegram bots in POLLING mode for local development
INFO: Webhooks deleted, starting polling...
INFO: ✅ Both bots are now running in polling mode
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

---

## Development Workflow

### Making Code Changes

1. **Edit code** in your IDE (VSCode, PyCharm, etc.)
2. **Save file**
3. **Changes auto-reload** in ~1 second!

Watch the logs:
```bash
docker logs -f impact-narrative-db-local
```

You'll see:
```
INFO: Will watch for changes in these directories: ['/app']
INFO: Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO: Started reloader process [1]
```

### Stopping the Server
```bash
docker compose -f docker-compose.local.yml down
```

### Rebuilding (only when dependencies change)
```bash
# If you modified requirements.txt or Dockerfile
docker compose -f docker-compose.local.yml build
docker compose -f docker-compose.local.yml up
```

---

## Polling vs Webhook

### Local Development (Polling Mode)
- ✅ No ngrok/Cloudflare needed
- ✅ No webhook configuration
- ✅ Bot fetches messages from Telegram
- ✅ Perfect for development

**Automatically enabled** when `USE_POLLING=true` in `.env.local`

### Test/Production (Webhook Mode)
- Messages pushed to your server via HTTPS
- Real-time, efficient
- Requires public URL

**Automatically enabled** on AWS Lightsail (no `USE_POLLING` in `.env.test`)

---

## Useful Commands

### View Logs
```bash
# Real-time logs
docker logs -f impact-narrative-db-local

# Last 100 lines
docker logs --tail 100 impact-narrative-db-local
```

### Enter Container
```bash
docker exec -it impact-narrative-db-local bash

# Inside container
ls /app
python -c "import chromadb; print(chromadb.__version__)"
```

### Check Health
```bash
curl http://localhost:8000/healthz
# {"ok":true,"time":"2026-01-09T..."}
```

### Clean Up
```bash
# Stop and remove containers
docker compose -f docker-compose.local.yml down

# Remove volumes (careful: deletes ChromaDB data!)
docker compose -f docker-compose.local.yml down -v

# Remove images
docker rmi impact-db-app
```

---

## Troubleshooting

### Build Failed
```bash
# Check Docker is running
docker ps

# Check available disk space
df -h

# Try rebuilding from scratch
docker compose -f docker-compose.local.yml build --no-cache
```

### Module Not Found
```bash
# Dependency issue - rebuild
docker compose -f docker-compose.local.yml build
```

### Webhook Already Set Error
```bash
# Delete webhooks manually
curl -X POST "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"
```

### Port 8000 Already in Use
```bash
# Find what's using port 8000
lsof -i :8000

# Kill process or change port in docker-compose.local.yml
ports:
  - "8001:8000"  # Use 8001 instead
```

---

## Architecture

### File Structure
```
impact-db/
├── docker-compose.local.yml    # Local development config
├── docker-compose.yml          # Test/production config
├── .env.local                  # Local environment (gitignored)
├── .env.local.template         # Template for local env
├── project/                    # Source code (volume mounted)
│   ├── main.py                # FastAPI app + Polling mode
│   ├── narrative_app/         # Narrative bot logic
│   ├── impact_app/            # Impact bot logic
│   └── core/                  # Shared utilities
└── credentials/               # API credentials (gitignored)
```

### How Hot Reload Works

1. Code in `./project` is **mounted** into container at `/app/project`
2. Uvicorn watches for file changes with `--reload`
3. On change, Uvicorn restarts the app automatically
4. No rebuild needed!

### Volume Mounts
```yaml
volumes:
  - ./project:/app/project       # Code (hot reload)
  - ./.env.local:/app/.env       # Environment
  - ./credentials:/app/credentials  # Google Cloud key
  - ./.chroma_categories:/app/.chroma_categories  # Vector DB
  - ./.runtime:/app/.runtime     # Runtime files
```

---

## Best Practices

### DO ✅
- Use Polling mode for local development
- Commit code frequently
- Test locally before pushing
- Keep `.env.local` secure (never commit!)
- Use Docker for environment consistency

### DON'T ❌
- Commit `.env.local` to Git
- Use production API keys locally
- Set webhooks in local development
- Modify `docker-compose.yml` for local changes

---

## Deploying to Test Environment

Once your feature is ready:

```bash
# 1. Commit and push
git add .
git commit -m "Feature: your feature description"
git push origin feature/create_docker_environment

# 2. SSH to test server
ssh -i ~/.ssh/key.pem ubuntu@test.gopal-tech.com

# 3. Update and restart
cd impact-db
git pull origin feature/create_docker_environment
docker compose down
docker compose build
docker compose up -d

# 4. Check logs
docker logs -f impact-narrative-db
```

---

## FAQ

**Q: Do I need to install Python/ffmpeg locally?**
A: No! Everything runs in Docker.

**Q: Can I use venv instead of Docker?**
A: Yes, but Docker is recommended for environment consistency.

**Q: How do I switch between Polling and Webhook?**
A: Set `USE_POLLING=true` in `.env.local` (Polling) or `USE_POLLING=false` (Webhook).

**Q: Do I need ngrok?**
A: No, not with Polling mode!

**Q: Can multiple developers work on the same bot?**
A: Each developer should create their own bot tokens for local development.

---

## Next Steps

- Read [SETUP_GUIDE.md](./SETUP_GUIDE.md) for detailed setup
- Read [DEVELOPMENT_GUIDE.md](./DEVELOPMENT_GUIDE.md) for architecture overview
- Check [log/](./log/) for deployment history

Happy coding! 🚀
