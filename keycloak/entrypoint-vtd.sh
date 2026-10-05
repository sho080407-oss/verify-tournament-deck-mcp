#!/bin/sh
set -eu

: "${VTD_REVIEWER_PASSWORD:?VTD_REVIEWER_PASSWORD is required}"
: "${KEYCLOAK_ADMIN_USER:=admin}"
: "${KEYCLOAK_ADMIN_PASSWORD:?KEYCLOAK_ADMIN_PASSWORD is required}"

export KC_BOOTSTRAP_ADMIN_USERNAME="${KEYCLOAK_ADMIN_USER}"
export KC_BOOTSTRAP_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD}"
export KC_PROXY_HEADERS="${KC_PROXY_HEADERS:-xforwarded}"
export KC_HTTP_ENABLED=true

if [ -n "${PORT:-}" ]; then
  export KC_HTTP_PORT="${PORT}"
fi

if [ -z "${KC_HOSTNAME:-}" ] && [ -n "${RAILWAY_PUBLIC_DOMAIN:-}" ]; then
  export KC_HOSTNAME="https://${RAILWAY_PUBLIC_DOMAIN}"
fi

IMPORT_DIR=/opt/keycloak/data/import
TEMPLATE="$IMPORT_DIR/vtd-realm-import.template.json"
REALM_FILE="$IMPORT_DIR/vtd-realm.json"

escaped_password=$(printf '%s' "$VTD_REVIEWER_PASSWORD" | sed 's/[&|]/\\&/g')
sed "s|__VTD_REVIEWER_PASSWORD__|${escaped_password}|g" "$TEMPLATE" > "$REALM_FILE"

exec /opt/keycloak/bin/kc.sh start --optimized --import-realm
