# Windows Setup Guide - Local Development with Docker

This guide will help you set up the Impact/Narrative DB project on Windows from scratch using Docker.

## Prerequisites

### Required Software

1. **Git for Windows**
   - Download: https://git-scm.com/download/win
   - Use default settings during installation

2. **Docker Desktop for Windows**
   - Download: https://www.docker.com/products/docker-desktop/
   - Requirements: Windows 10/11 Pro, Enterprise, or Education (64-bit)
   - Enable WSL 2 during installation (recommended)

3. **Text Editor** (choose one)
   - VS Code: https://code.visualstudio.com/
   - Notepad++: https://notepad-plus-plus.org/
   - Or any editor you prefer

### System Requirements

- Windows 10 64-bit: Pro, Enterprise, or Education (Build 19041 or higher)
- Or Windows 11 64-bit
- At least 4GB RAM (8GB recommended)
- At least 10GB free disk space

---

## Step 1: Install Git

1. Download Git installer from https://git-scm.com/download/win
2. Run the installer
3. Use default settings (recommended)
4. Open **Git Bash** or **PowerShell** to verify installation:

```powershell
git --version
# Should output: git version 2.x.x
```

---

## Step 2: Install Docker Desktop

1. Download Docker Desktop from https://www.docker.com/products/docker-desktop/
2. Run the installer
3. **Important**: Enable WSL 2 when prompted
4. Restart your computer when installation completes
5. Start Docker Desktop from the Start menu
6. Wait for Docker to finish starting (whale icon in system tray)
7. Verify installation:

```powershell
docker --version
# Should output: Docker version 24.x.x or higher

docker compose version
# Should output: Docker Compose version v2.x.x or higher
```

---

## Step 3: Clone the Repository

Open **PowerShell** or **Git Bash** and run:

```powershell
# Navigate to your preferred directory (e.g., Desktop)
cd ~\Desktop

# Clone the repository
git clone https://github.com/rui12212/impact-db.git

# Navigate into the project
cd impact-db

# Switch to the development branch
git checkout feature/create_docker_environment

# Verify you're on the correct branch
git branch
# Should show: * feature/create_docker_environment
```

---

## Step 4: Set Up Environment Variables

1. Copy the environment template:

```powershell
# In PowerShell
Copy-Item .env.local.template .env.local
```

2. Open `.env.local` in your text editor (VS Code, Notepad++, etc.)

3. Fill in the required values:

```bash
# Required: Get these from your team lead
OPENAI_API_KEY=your-openai-api-key-here
NARRATIVE_TELEGRAM_BOT_TOKEN=your-narrative-bot-token-here
IMPACT_TELEGRAM_BOT_TOKEN=your-impact-bot-token-here
NOTION_API_KEY=your-notion-api-key-here

# Notion Database IDs (get from team lead)
NOTION_SCHOOLS_DB_ID=your-schools-db-id
NOTION_TEACHERS_DB_ID=your-teachers-db-id
NOTION_NARRATIVE_DB_ID=your-narrative-db-id
NOTION_IMPACT_DB_ID=your-impact-db-id
NOTION_STAFF_NARRATIVE_DB_ID=your-staff-narrative-db-id
NOTION_CATEGORIES_DB_ID=your-categories-db-id

# These can stay as default
ENVIRONMENT=local
USE_POLLING=true
PUBLIC_BASE_URL=http://localhost:8000
CATEGORY_MODE=hybrid
CHROMA_DIR=.chroma_categories
NARRATIVE_WINDOW_MINUTES=1
```

4. Save the file

---

## Step 5: Add Google Cloud Credentials

1. Get the `service-account.json` file from your team lead
2. Create the credentials folder and copy the file:

```powershell
# Create credentials directory
New-Item -ItemType Directory -Force -Path credentials

# Copy the service account file
# Replace "path\to\your\service-account.json" with actual path
Copy-Item "path\to\your\service-account.json" credentials\service-account.json
```

---

## Step 6: Build and Start Docker

### First Time Setup (Takes 3-5 minutes)

```powershell
# Build the Docker image
docker compose -f docker-compose.local.yml build

# This will:
# - Download Python 3.10 base image
# - Install all dependencies (137 packages)
# - Install ffmpeg and other tools
# - Build the application image
```

### Start the Application

```powershell
# Start in foreground (see logs in real-time)
docker compose -f docker-compose.local.yml up

# OR start in background (detached mode)
docker compose -f docker-compose.local.yml up -d
```

### Expected Output

You should see:

```
INFO:impactdb:Starting Telegram bots in POLLING mode for local development
INFO:impactdb:Webhooks deleted, starting polling...
INFO:impactdb:✅ Both bots are now running in polling mode
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

✅ **Success!** The application is now running.

---

## Step 7: Verify Installation

### Check Health Endpoint

Open PowerShell and run:

```powershell
curl http://localhost:8000/healthz
```

Expected response:
```json
{"ok":true,"time":"2026-01-09T..."}
```

### Test with Telegram

1. Open Telegram on your phone or desktop
2. Find the bot your team lead shared with you
3. Send a message
4. Check Docker logs to see it being processed

---

## Daily Development Workflow

### Starting Work

```powershell
# Navigate to project
cd ~\Desktop\impact-db

# Make sure Docker Desktop is running
# (Check system tray for whale icon)

# Start the application
docker compose -f docker-compose.local.yml up
```

### Making Code Changes

1. Edit files in the `project/` folder using your editor
2. Save the file
3. **Changes automatically reload in ~1 second!**
4. Check the console to see the reload message

### Viewing Logs

```powershell
# If running in background, view logs with:
docker logs -f impact-narrative-db-local

# Press Ctrl+C to stop viewing (container keeps running)
```

### Stopping Work

```powershell
# If running in foreground: Press Ctrl+C

# If running in background:
docker compose -f docker-compose.local.yml down
```

---

## Common Commands Reference

### Docker Commands

```powershell
# Start application
docker compose -f docker-compose.local.yml up

# Start in background
docker compose -f docker-compose.local.yml up -d

# Stop application
docker compose -f docker-compose.local.yml down

# View logs (if running in background)
docker logs -f impact-narrative-db-local

# Restart application
docker compose -f docker-compose.local.yml restart

# Rebuild after dependency changes
docker compose -f docker-compose.local.yml build

# Check running containers
docker ps

# Access container shell (for debugging)
docker exec -it impact-narrative-db-local bash
```

### Git Commands

```powershell
# Check current branch
git branch

# Pull latest changes
git pull origin feature/create_docker_environment

# Check status
git status

# Create a new branch for your work
git checkout -b feature/your-feature-name

# Stage changes
git add .

# Commit changes
git commit -m "Your commit message"

# Push changes
git push origin feature/your-feature-name
```

---

## Troubleshooting

### Issue: Docker Desktop won't start

**Solution:**
1. Make sure Hyper-V and WSL 2 are enabled
2. Open PowerShell as Administrator and run:
```powershell
wsl --install
wsl --set-default-version 2
```
3. Restart your computer
4. Start Docker Desktop again

### Issue: "port 8000 is already in use"

**Solution:**
1. Find what's using port 8000:
```powershell
netstat -ano | findstr :8000
```
2. Kill the process or change port in `docker-compose.local.yml`:
```yaml
ports:
  - "8001:8000"  # Use 8001 instead
```

### Issue: Build fails with "no space left on device"

**Solution:**
1. Clean up Docker:
```powershell
docker system prune -a
```
2. In Docker Desktop settings, increase disk space allocation

### Issue: "python-telegram-bot" not found

**Solution:**
```powershell
# Rebuild the image
docker compose -f docker-compose.local.yml build --no-cache
docker compose -f docker-compose.local.yml up
```

### Issue: Changes not reloading

**Solution:**
1. Make sure you're editing files in `project/` folder
2. Check Docker logs for errors
3. Try restarting:
```powershell
docker compose -f docker-compose.local.yml restart
```

### Issue: Can't access http://localhost:8000

**Solution:**
1. Check if Docker container is running:
```powershell
docker ps
```
2. Check Docker logs for errors:
```powershell
docker logs impact-narrative-db-local
```
3. Make sure Docker Desktop is running

---

## Getting Help

### Check Logs

Always check logs first when something isn't working:

```powershell
docker logs impact-narrative-db-local
```

### Ask Your Team

If you're stuck:
1. Copy the error message from logs
2. Note what you were trying to do
3. Ask your team lead for help

### Useful Resources

- Project documentation: `docs/` folder
- Local development guide: `docs/LOCAL_DEVELOPMENT.md`
- Deployment logs: `docs/log/` folder

---

## Next Steps

Now that you have the project running locally:

1. Read `docs/DEVELOPMENT_GUIDE.md` for architecture overview
2. Read `docs/LOCAL_DEVELOPMENT.md` for detailed development workflow
3. Explore the codebase in the `project/` folder
4. Try making a small change and see it reload automatically!

---

## Quick Reference Card

### 🚀 Start Development
```powershell
cd ~\Desktop\impact-db
docker compose -f docker-compose.local.yml up
```

### 🛑 Stop Development
```powershell
# Press Ctrl+C (if in foreground)
# OR
docker compose -f docker-compose.local.yml down
```

### 📝 View Logs
```powershell
docker logs -f impact-narrative-db-local
```

### 🔄 Rebuild (after pulling changes)
```powershell
docker compose -f docker-compose.local.yml build
docker compose -f docker-compose.local.yml up
```

### ✅ Check Health
```powershell
curl http://localhost:8000/healthz
```

---

## Summary

You've successfully set up the development environment! 🎉

**What you can do now:**
- Edit code and see changes instantly
- Test Telegram bots locally without webhooks
- Work on the same environment as the team
- Commit and push your changes to GitHub

**Remember:**
- Always pull latest changes before starting work
- Always commit your changes before stopping work
- Ask for help when you're stuck!

Happy coding! 🚀
