#!/bin/bash
# NEXUM v9 Setup Script
set -e

echo "════════════════════════════════════════════"
echo "  NEXUM v9 Setup — OpenClaw-grade features"
echo "════════════════════════════════════════════"
echo ""

# Check Node.js
if ! command -v node &> /dev/null; then
  echo "❌ Node.js not found. Install from https://nodejs.org (v20+)"
  exit 1
fi

NODE_VER=$(node -e "process.exit(parseInt(process.version.slice(1)) < 20 ? 1 : 0)" && echo "ok" || echo "old")
if [ "$NODE_VER" = "old" ]; then
  echo "❌ Node.js v20+ required (current: $(node --version))"
  exit 1
fi
echo "✅ Node.js $(node --version)"

# Install npm deps
echo ""
echo "📦 Installing dependencies..."
npm install

# Install Playwright browsers
echo ""
echo "🌐 Installing Chromium browser for browser automation..."
npx playwright install chromium
echo "✅ Chromium installed"

# Create .env if not exists
if [ ! -f .env ]; then
  echo ""
  echo "⚙️  Creating .env from .env.example..."
  cp .env.example .env 2>/dev/null || cat > .env << 'EOF'
# ── Required ──────────────────────────────────────────────────
BOT_TOKEN=your_telegram_bot_token_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# ── Optional ──────────────────────────────────────────────────
# OpenAI (for vector memory embeddings + Whisper + Image gen)
OPENAI_API_KEY=

# Web app URL (for website sharing)
WEBAPP_URL=http://localhost:3000

# Allowed Telegram user IDs (comma-separated, leave empty for all)
ALLOWED_USERS=

# Chrome CDP URL (for connecting to existing Chrome)
# CHROME_CDP_URL=http://localhost:9222
EOF
  echo "✅ Created .env — please fill in your tokens!"
fi

# Create data directory
mkdir -p data
echo "✅ Data directory ready"

echo ""
echo "════════════════════════════════════════════"
echo "  Setup complete!"
echo "════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Edit .env — add BOT_TOKEN and ANTHROPIC_API_KEY"
echo "  2. npm start — launch the bot"
echo ""
echo "New commands (v9):"
echo "  🌐 Browser:    /browse /bclick /bfill /bsnap /beval /bscroll /btext /gsearch /btabs"
echo "  🧠 Mem:        /vmem <query> /vmemstats /vmemclear"
echo "  🤖 Subagents:  /agent /agentmany /agentwait /agentlist /agentcancel"
echo ""
