docker stop slopstudy

ENV=/mnt/user/appdata/flashdeck/.env

# Public hosting settings + local SearXNG (idempotent). Invite links + emails use APP_BASE_URL.
sed -i '/^APP_BASE_URL=/d;/^COOKIE_SECURE=/d;/^SEARXNG_URL=/d' "$ENV"
cat >> "$ENV" <<'EOF'
APP_BASE_URL=https://flash.giziko.online
COOKIE_SECURE=true
SEARXNG_URL=http://192.168.1.238:8089
EOF

# Latest code from GitHub
rm -rf /mnt/user/appdata/flashdeck/src
git clone https://github.com/martinkadauke/slopstudy.git /mnt/user/appdata/flashdeck/src

# Build + swap (keeps data volume + .env; DB auto-migrates)
docker build -t slopstudy:latest /mnt/user/appdata/flashdeck/src
docker rm -f slopstudy flashdeck 2>/dev/null
docker run -d --name slopstudy --restart unless-stopped \
  -p 8090:8000 \
  -v /mnt/user/appdata/flashdeck/data:/data \
  --env-file "$ENV" \
  --add-host host.docker.internal:host-gateway \
  slopstudy:latest

# Verify
sleep 8
docker ps --filter name=slopstudy --format '{{.Names}}: {{.Status}}'
curl -s http://127.0.0.1:8090/api/health && echo
docker logs slopstudy 2>&1 | grep -iE "migrat|worker started|startup complete" | tail -5