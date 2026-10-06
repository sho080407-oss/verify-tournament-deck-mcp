FROM python:3.12-slim AS engine-build

RUN apt-get update && apt-get install -y --no-install-recommends \
    git g++ meson ninja-build ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN git clone --depth 1 --recurse-submodules --shallow-submodules \
      https://github.com/edo9300/ygopro-core.git /build/ygopro-core \
    && sed -i "s/, 'backend_startup_project=ocgcore'//" /build/ygopro-core/meson.build \
    && meson setup /build/ygopro-core/build /build/ygopro-core \
      -Ddefault_library=shared -Dbuildtype=release \
    && meson compile -C /build/ygopro-core/build

RUN git clone --depth 1 https://github.com/ProjectIgnis/CardScripts.git /build/CardScripts \
    && git clone --depth 1 https://github.com/ProjectIgnis/BabelCDB.git /build/BabelCDB

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDOPRO_SIM_ROOT=/opt/edopro-sim \
    LD_LIBRARY_PATH=/opt/edopro-sim/lib

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN mkdir -p /opt/edopro-sim/lib /opt/edopro-sim/CardScripts /opt/edopro-sim/BabelCDB

COPY --from=engine-build /build/ygopro-core/build/libocgcore.so /opt/edopro-sim/lib/libocgcore.so
COPY --from=engine-build /build/CardScripts /opt/edopro-sim/CardScripts
COPY --from=engine-build /build/BabelCDB/cards.cdb /opt/edopro-sim/BabelCDB/cards.cdb
COPY server.py /app/server.py

EXPOSE 10000

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers"]
