# TAK Server stub for the CICS TAK PoC.
#
# This image runs a minimal asyncio TCP+TLS server on :8089 that accepts
# newline-delimited CoT XML and logs every event. It exists so developers
# can exercise the full sensor → gateway → TAK pipeline without needing a
# TAK.gov account or the official TAK Server image.
#
# For production, swap the `tak-server` service in docker-compose.yaml for
# the real TAK Server image as documented in README.md.

FROM python:3.12-slim

# No third-party deps; stdlib only (asyncio, ssl, logging, json).
# We only need a well-known label for ops tooling.
LABEL org.opencontainers.image.title="cics-tak-demo TAK Server stub"
LABEL org.opencontainers.image.description="Self-contained TLS CoT collector for PoC"

WORKDIR /app
COPY stub_server.py /app/stub_server.py

# Default cert layout (overridable via volume mounts + CMD args).
ENV TAK_CERT=/certs/takserver.crt \
    TAK_KEY=/certs/takserver.key \
    TAK_CA=/certs/ca.crt \
    TAK_PORT=8089 \
    LOG_LEVEL=INFO

EXPOSE 8089

# Healthcheck: ensure the TLS port is open.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import socket,sys; s=socket.socket(); s.settimeout(2); \
        sys.exit(0 if s.connect_ex(('127.0.0.1',int('${TAK_PORT}')))==0 else 1)"

ENTRYPOINT ["python3", "/app/stub_server.py"]
CMD ["--host", "0.0.0.0", "--port", "8089", \
     "--cert", "/certs/takserver.crt", \
     "--key",  "/certs/takserver.key", \
     "--ca",   "/certs/ca.crt", \
     "--output-dir", "/var/log/tak-stub"]
