#!/usr/bin/env bash
set -e

echo "=================================================="
echo "🥥 Updating Thenga Network Bot & Dashboard"
echo "=================================================="

# Navigate to project directory
cd "$(dirname "$0")"

# 1. Pull latest changes from GitHub
echo "📥 [1/3] Pulling latest code from GitHub..."
git pull origin main

# 2. Update Python dependencies if changed
echo "📦 [2/3] Cleaning cache and installing dependencies..."
python3 -m pip uninstall -y yt-dlp 2>/dev/null || true
python3 -m pip cache purge 2>/dev/null || true
python3 -m pip install --no-cache-dir -U "yt-dlp[default]"
python3 -m pip install -r requirements.txt

# 3. Restart PM2 process
echo "🚀 [3/3] Restarting bot service..."
pm2 restart thenga-bot

echo "=================================================="
echo "✅ Thenga Bot successfully updated and restarted!"
echo "=================================================="
pm2 status thenga-bot
