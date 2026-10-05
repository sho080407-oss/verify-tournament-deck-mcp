# verify-tournament-deck RC6 public fast track

Deployment repository for **v20.18.25 / Bridge 26 / RC6**.

This repository is intended for a production Render deployment of the remote MCP server without changing the frozen verifier core.

## Deploy

1. Import this repository into Render using `render.yaml`.
2. Set the required environment variables shown in `.env.production.example`.
3. Deploy and confirm `/healthz` is healthy.
4. Use the assigned hostname with `derive_submission_inputs.py` to produce the final OpenAI Directory submission inputs.
5. Run `scripts/final_public_release.py` with real publisher/OAuth/reviewer inputs.

See `FAST_TRACK_DEPLOYMENT.md` for the complete handoff.

## Security

Do not commit real `.env` files, OAuth client secrets, reviewer tokens, private keys, or OpenAI domain-challenge tokens.
