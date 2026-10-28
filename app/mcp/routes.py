# -*- coding: utf-8 -*-
"""
Sewa Setu MCP HTTP Routes
Exposes Streamable HTTP transports for Citizen and Admin MCP servers.
"""

import json
from flask import Blueprint, request, jsonify, Response, stream_with_context

try:
    from app.mcp.citizen_server import process_citizen_mcp_request, CITIZEN_TOOLS
    from app.mcp.admin_server import process_admin_mcp_request, verify_admin_token, ADMIN_TOOLS
except (ImportError, ModuleNotFoundError):
    from mcp.citizen_server import process_citizen_mcp_request, CITIZEN_TOOLS
    from mcp.admin_server import process_admin_mcp_request, verify_admin_token, ADMIN_TOOLS

mcp_bp = Blueprint("mcp", __name__, url_prefix="/mcp")


def _get_admin_token(req):
    """Extract admin token from Authorization, X-Admin-Token, or X-API-Key headers."""
    auth_header = req.headers.get("Authorization")
    if auth_header:
        return auth_header
    admin_token = req.headers.get("X-Admin-Token")
    if admin_token:
        return admin_token
    api_key = req.headers.get("X-API-Key")
    if api_key:
        return api_key
    # Also check query param ?token=
    token_param = req.args.get("token")
    if token_param:
        return token_param
    return None


# ---------------------------------------------------------------------------
# Citizen MCP Endpoints (/mcp/citizen)
# ---------------------------------------------------------------------------

@mcp_bp.route("/citizen", methods=["GET"])
def citizen_mcp_info():
    """Service metadata and tool discovery for Citizen MCP."""
    accept = request.headers.get("Accept", "")
    if "text/event-stream" in accept:
        # SSE stream heartbeat / initial announcement
        def event_stream():
            data = json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/message",
                "params": {"message": "Citizen MCP endpoint stream active"}
            })
            yield f"data: {data}\n\n"
        return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

    return jsonify({
        "status": "healthy",
        "service": "sewasetu-citizen-mcp",
        "protocolVersion": "2024-11-05",
        "transport": "streamable-http",
        "description": "Public MCP server for citizens and advocate agents accessing the Sewa Setu Old Age Pension Portal.",
        "tools_count": len(CITIZEN_TOOLS),
        "tools": [t["name"] for t in CITIZEN_TOOLS]
    }), 200


@mcp_bp.route("/citizen/health", methods=["GET"])
def citizen_mcp_health():
    """Dedicated health check for citizen MCP service."""
    return jsonify({
        "status": "healthy",
        "service": "sewasetu-citizen-mcp"
    }), 200


@mcp_bp.route("/citizen", methods=["POST"])
def citizen_mcp_handler():
    """Handle JSON-RPC 2.0 requests for Citizen MCP server."""
    payload = request.get_json(force=True, silent=True)
    if payload is None:
        return jsonify({
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: Valid JSON body required."}
        }), 400

    accept = request.headers.get("Accept", "")
    is_sse = "text/event-stream" in accept

    if isinstance(payload, list):
        results = [process_citizen_mcp_request(req) for req in payload]
        results = [r for r in results if r is not None]
        if is_sse:
            def event_stream():
                for res in results:
                    yield f"data: {json.dumps(res)}\n\n"
            return Response(stream_with_context(event_stream()), mimetype="text/event-stream")
        return jsonify(results), 200

    response = process_citizen_mcp_request(payload)
    if response is None:
        # Notification - return empty 204 No Content
        return "", 204

    if is_sse:
        def event_stream():
            yield f"data: {json.dumps(response)}\n\n"
        return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

    return jsonify(response), 200


# ---------------------------------------------------------------------------
# Administrator MCP Endpoints (/mcp/admin)
# ---------------------------------------------------------------------------

@mcp_bp.route("/admin", methods=["GET"])
def admin_mcp_info():
    """Service metadata for Admin MCP. Requires administrative authentication."""
    token = _get_admin_token(request)
    is_valid, user = verify_admin_token(token)
    if not is_valid:
        return jsonify({
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32000,
                "message": "Unauthorized: Valid administrator bearer token required for Administrator MCP."
            }
        }), 401, {"WWW-Authenticate": 'Bearer realm="SewaSetuAdminMCP"'}

    return jsonify({
        "status": "healthy",
        "service": "sewasetu-admin-mcp",
        "protocolVersion": "2024-11-05",
        "transport": "streamable-http",
        "authenticated_user": user,
        "description": "Administrator MCP server for Department officers and assessors.",
        "tools_count": len(ADMIN_TOOLS),
        "tools": [t["name"] for t in ADMIN_TOOLS]
    }), 200


@mcp_bp.route("/admin/health", methods=["GET"])
def admin_mcp_health():
    """Dedicated health check for admin MCP service."""
    return jsonify({
        "status": "healthy",
        "service": "sewasetu-admin-mcp"
    }), 200


@mcp_bp.route("/admin", methods=["POST"])
def admin_mcp_handler():
    """Handle JSON-RPC 2.0 requests for Admin MCP server with strict auth enforcement."""
    token = _get_admin_token(request)
    payload = request.get_json(force=True, silent=True)
    if payload is None:
        return jsonify({
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: Valid JSON body required."}
        }), 400

    # Strict Authentication Enforcement
    # Allow initialize / ping without auth for protocol discovery if needed, but reject all tools/list and tools/call
    method = payload.get("method") if isinstance(payload, dict) else ""
    is_valid, user = verify_admin_token(token)

    if not is_valid and method not in ("initialize", "ping", "notifications/initialized", "initialized"):
        req_id = payload.get("id") if isinstance(payload, dict) else None
        return jsonify({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32000,
                "message": "Unauthorized: Valid administrator bearer token required for Administrator MCP tools."
            }
        }), 403

    accept = request.headers.get("Accept", "")
    is_sse = "text/event-stream" in accept

    if isinstance(payload, list):
        results = [process_admin_mcp_request(req, token) for req in payload]
        results = [r for r in results if r is not None]
        if is_sse:
            def event_stream():
                for res in results:
                    yield f"data: {json.dumps(res)}\n\n"
            return Response(stream_with_context(event_stream()), mimetype="text/event-stream")
        return jsonify(results), 200

    response = process_admin_mcp_request(payload, token)
    if response is None:
        return "", 204

    if is_sse:
        def event_stream():
            yield f"data: {json.dumps(response)}\n\n"
        return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

    return jsonify(response), 200
