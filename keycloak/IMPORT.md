# Keycloak vtd realm import

Current Keycloak:

`https://keycloak-production-1811.up.railway.app`

## Minimal manual steps

1. Open the Keycloak Administration Console.
2. Sign in to the `master` realm as `admin`.
3. Retrieve `KEYCLOAK_ADMIN_PASSWORD` from the Railway `Keycloak` service Variables page.
4. From the realm selector, choose **Create realm**.
5. Import `keycloak/vtd-realm-import.json` as the Resource file and create the realm.
6. In realm `vtd`, open **Users** -> `openai-reviewer` -> **Credentials**.
7. Set a strong non-temporary password.

## Expected configuration

- Realm: `vtd`
- Client: `chatgpt-vtd`
- Public client: yes
- Authorization Code flow: enabled
- PKCE: S256
- Direct Access Grants: disabled
- Redirect URI: `https://chatgpt.com/connector_platform_oauth_redirect`
- Optional scope: `deck:verify`
- Access-token audience: `https://verify-tournament-deck-mcp-production.up.railway.app/mcp`

## Verification endpoints

- Discovery: `https://keycloak-production-1811.up.railway.app/realms/vtd/.well-known/openid-configuration`
- JWKS: `https://keycloak-production-1811.up.railway.app/realms/vtd/protocol/openid-connect/certs`

RC6 already has the matching OIDC issuer/discovery configuration staged in Railway variables.
Do not redeploy RC6 until the `vtd` realm has been imported.
