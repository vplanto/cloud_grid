# ==============================================================================
# Dockerfile: Production-Ready Container for Monte Carlo Simulation Service
# Course: Cloud and Grid Systems (Stage 3: Docker & Web)
# ==============================================================================

# 1. Base Image: Slim Debian-based Python (pre-compiled C-extensions, glibc support)
FROM python:3.11-slim

# 2. Environment Flags:
# - PYTHONUNBUFFERED=1: Stream stdout/stderr directly (no buffered logs)
# - PYTHONDONTWRITEBYTECODE=1: Avoid .pyc clutter in container layers
# - PORT=8080: Default listening port
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    SIM_WORKERS=4

WORKDIR /app

# 3. Layer Caching: Install dependencies first (infrequently changed layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Security Best Practice: Create and switch to non-root user (Principle of Least Privilege)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -m appuser

# 5. Application Code Layer (frequently changed layer)
COPY --chown=appuser:appgroup app.py .

# 6. Switch to non-root user
USER appuser

# 7. Document exposed port
EXPOSE 8080

# 8. Healthcheck for Container Orchestration (Docker / K8s)
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + str(__import__('os').environ.get('PORT', 8080)) + '/api/health')" || exit 1

# 9. Exec form ENTRYPOINT: passes Linux signals (SIGTERM/SIGINT) directly to Python process (PID 1)
ENTRYPOINT ["python", "app.py"]
