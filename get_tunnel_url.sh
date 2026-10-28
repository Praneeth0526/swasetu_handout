#!/usr/bin/env bash
# ==============================================================================
# Helper to retrieve the active Cloudflare Tunnel public URL
# ==============================================================================

if [ -n "$CLOUDFLARE_TUNNEL_TOKEN" ]; then
    echo "[Tunnel] Configured with Named Tunnel token. Your tunnel is mapped to your configured Cloudflare dashboard domain."
else
    URL=$(docker compose logs tunnel 2>/dev/null | grep -oE "https://[a-zA-Z0-9-]+\.trycloudflare\.com" | tail -n 1)
    if [ -n "$URL" ]; then
        echo "=========================================================="
        echo " Public Cloudflare Tunnel URL:"
        echo " $URL"
        echo "=========================================================="
        echo " - Portal Home:          $URL/"
        echo " - Citizen MCP Endpoint: $URL/mcp/citizen"
        echo " - Admin MCP Endpoint:   $URL/mcp/admin"
        echo " - Evaluation Dashboard: $URL/evals"
        echo " - System Health Check:  $URL/health"
        echo "=========================================================="
    else
        echo "[Tunnel] Tunnel URL not yet found in logs. Check if stack is running:"
        echo "  docker compose up -d"
        echo "  docker compose logs -f tunnel"
    fi
fi
