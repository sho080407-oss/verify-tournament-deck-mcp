from __future__ import annotations
import os
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from public_site import wrap_app

def _challenge(_):
    token = (os.environ.get("OPENAI_APPS_CHALLENGE_TOKEN") or "").strip()
    if not token:
        return PlainTextResponse("not configured", status_code=404)
    return PlainTextResponse(token, media_type="text/plain")

async def health(_):
    return JSONResponse({
        "ok": True,
        "service": "verify-tournament-deck",
        "mode": "public-bootstrap",
        "mcp_auth_configured": False,
    })

async def ready(_):
    return JSONResponse({
        "ok": False,
        "reason": "oauth_not_configured",
        "mcp_url": os.environ.get("VTD_PUBLIC_MCP_URL", ""),
    }, status_code=503)

async def oauth_metadata(_):
    return JSONResponse({"error": "oauth_not_configured"}, status_code=503)

async def mcp_blocked(_):
    return JSONResponse({"error": "oauth_not_configured"}, status_code=503)

async def challenge(request):
    return _challenge(request)

def _bootstrap_app():
    try:
        from production_server import app as rc6_app
        return wrap_app(rc6_app)
    except Exception:
        inner = Starlette(routes=[
            Route("/healthz", health),
            Route("/readyz", ready),
            Route("/.well-known/openai-apps-challenge", challenge),
            Route("/.well-known/oauth-protected-resource", oauth_metadata),
            Route("/mcp", mcp_blocked, methods=["GET", "POST", "DELETE", "OPTIONS"]),
        ])
        return wrap_app(inner)

app = _bootstrap_app()
