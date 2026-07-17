# elk-os-mocks: Matomo + Migadu shaped mock APIs for the demo box.
# Stdlib-only Python; no pip install layer, so the build is fast and
# reproducible offline once the base image is present.
FROM python:3.12-slim

WORKDIR /app
COPY mock-integrations.py /app/mock-integrations.py

ENV PORT=8080
EXPOSE 8080

# python:3.12-slim ships neither wget nor curl; probe with python itself
# (same convention as the portal healthcheck in compose.portal.yaml).
HEALTHCHECK --interval=15s --timeout=5s --retries=3 CMD \
  ["python3", "-c", "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=4).status==200 else 1)"]

CMD ["python3", "/app/mock-integrations.py"]
