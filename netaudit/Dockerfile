FROM python:3.12-slim

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

# Engagement data + uploaded evidence live here. Mount a persistent volume at
# /data on your host so nothing is lost when the container restarts.
ENV NETAUDIT_HOME=/data
VOLUME ["/data"]

# Cloud platforms inject $PORT; default to 8765 locally. Bind all interfaces so
# the platform's router can reach it. NETAUDIT_TOKEN MUST be set in the
# environment for a public deployment — it is the only access control.
EXPOSE 8765
CMD ["sh", "-c", "netaudit serve --host 0.0.0.0 --port ${PORT:-8765}"]
