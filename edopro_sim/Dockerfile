FROM python:3.12-slim AS engine-build

ARG OCGCORE_REF=38d04c9feb1a26617407091380634c87262fe3f8
ARG CARDSCRIPTS_REF=37f270dc813a12d123707ae255f2bda7922999c4
ARG BABELCDB_REF=fdf92aea31033cd6c44afa89987c5e00665205e2

RUN apt-get update && apt-get install -y --no-install-recommends \
    git g++ meson ninja-build ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN mkdir -p /build/ygopro-core \
    && cd /build/ygopro-core \
    && git init --quiet \
    && git remote add origin https://github.com/edo9300/ygopro-core.git \
    && git fetch --depth 1 origin "${OCGCORE_REF}" \
    && git checkout --quiet FETCH_HEAD \
    && git submodule update --init --recursive --depth 1 \
    && sed -i "s/, 'backend_startup_project=ocgcore'//" meson.build \
    && meson setup build . -Ddefault_library=shared -Dbuildtype=release \
    && meson compile -C build

RUN mkdir -p /build/CardScripts \
    && cd /build/CardScripts \
    && git init --quiet \
    && git remote add origin https://github.com/ProjectIgnis/CardScripts.git \
    && git fetch --depth 1 origin "${CARDSCRIPTS_REF}" \
    && git checkout --quiet FETCH_HEAD

RUN mkdir -p /build/BabelCDB \
    && cd /build/BabelCDB \
    && git init --quiet \
    && git remote add origin https://github.com/ProjectIgnis/BabelCDB.git \
    && git fetch --depth 1 origin "${BABELCDB_REF}" \
    && git checkout --quiet FETCH_HEAD

RUN printf '%s\n' \
    '{' \
    '  "bridge_version": "0.4.0",' \
    '  "rules_profile": "OCG Master Rule 5",' \
    '  "ocgcore_ref": "'"\${OCGCORE_REF}"'",' \
    '  "cardscripts_ref": "'"\${CARDSCRIPTS_REF}"'",' \
    '  "babelcdb_ref": "'"\${BABELCDB_REF}"'"' \
    '}' > /build/runtime-fingerprint.json

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDOPRO_SIM_ROOT=/opt/edopro-sim \
    LD_LIBRARY_PATH=/opt/edopro-sim/lib

WORKDIR /app

COPY requirements.txt /app/requirements.txt
# MCP 2.2.0 has a Streamable HTTP server/discover framing regression with
# auto-negotiating clients. Pin the v1 maintenance line so clients fall back to
# the stable legacy initialize/tools/list flow. This changes transport only.
RUN sed -i 's/^mcp==2\.2\.0$/mcp==1.30.0/' /app/requirements.txt \
    && pip install --no-cache-dir -r /app/requirements.txt

RUN mkdir -p /opt/edopro-sim/lib /opt/edopro-sim/CardScripts /opt/edopro-sim/BabelCDB

COPY --from=engine-build /build/ygopro-core/build/libocgcore.so /opt/edopro-sim/lib/libocgcore.so
COPY --from=engine-build /build/CardScripts /opt/edopro-sim/CardScripts
COPY --from=engine-build /build/BabelCDB/cards.cdb /opt/edopro-sim/BabelCDB/cards.cdb
COPY --from=engine-build /build/runtime-fingerprint.json /opt/edopro-sim/runtime-fingerprint.json
COPY server.py /app/server.py

# MCP SDK v1 compatibility shim: retain every EDOPro tool and only swap the
# server transport wrapper from MCPServer(v2) to FastMCP(v1).
RUN sed -i \
      -e 's/from mcp\.server\.mcpserver import MCPServer/from mcp.server.fastmcp import FastMCP/' \
      -e 's/mcp = MCPServer("verify-tournament-deck-edopro-sim")/mcp = FastMCP("verify-tournament-deck-edopro-sim", json_response=True)/' \
      /app/server.py \
    && sed -i '/^mcp_app = mcp\.streamable_http_app(/,/^)/c\mcp_app = mcp.streamable_http_app()' /app/server.py

EXPOSE 10000

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers"]
