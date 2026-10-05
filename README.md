# verify-tournament-deck MCP — RC6

Production deployment repository for **v20.18.25 / Bridge 26 / RC6**.

The frozen RC6 runtime is stored as `rc6_runtime_min.zip` and expanded during the Docker build.

## Render deployment

1. Create a Render Blueprint from this repository.
2. Set `VTD_AUTH_ISSUER_URL` to the production OIDC issuer.
3. Deploy and confirm `/healthz`.
4. Public MCP: `https://<render-host>/mcp`.
5. Public listing pages are served from the same host.

Do not commit OAuth secrets, reviewer tokens, private keys, real `.env` files, or OpenAI domain-challenge tokens.

RC6 runtime SHA-256: `a0745bb66bc4906f3eb13824475230325123656ac03ad545475bc94e16f89d78`


## Railway fast path

Railway can deploy this repository directly from the root Dockerfile.

Recommended service settings:
- Source: `sho080407-oss/verify-tournament-deck-mcp`
- Branch: `main`
- Healthcheck path: `/healthz`
- Public networking: enabled
- Do not override the start command; the Dockerfile already starts Uvicorn using Railway's injected `PORT`.

After Railway assigns a public domain, use:
- MCP: `https://<assigned-domain>/mcp`
- Website: `https://<assigned-domain>/`
- Support: `https://<assigned-domain>/support`
- Privacy: `https://<assigned-domain>/privacy`
- Terms: `https://<assigned-domain>/terms`
- Demo: `https://<assigned-domain>/demo`

Do not commit OAuth secrets or reviewer tokens.
