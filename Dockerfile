# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    QF_RUNTIME_ROOT=/var/lib/quant-factory

WORKDIR /app

RUN groupadd --gid 10001 qf && \
    useradd --uid 10001 --gid 10001 --create-home --home-dir /home/qf --shell /usr/sbin/nologin qf && \
    mkdir -p /var/lib/quant-factory && \
    chown qf:qf /var/lib/quant-factory

COPY requirements-runtime.txt /tmp/requirements-runtime.txt
RUN python -m pip install --no-cache-dir --requirement /tmp/requirements-runtime.txt

# A private additional build context supplies only the licensed wheel. BuildKit
# secrets have a 500 KiB limit; this read-only bind keeps the larger wheel out
# of image layers. No GitHub credential is sent to the builder.
RUN --mount=type=bind,from=vectorbt_private,target=/run/vectorbt-private,ro \
    python -m pip install --no-cache-dir /run/vectorbt-private/vectorbtpro-2026.4.7-py3-none-any.whl && \
    python -c "from importlib.metadata import version; assert version('vectorbtpro') == '2026.4.7'"

ARG QF_REVISION
ENV QF_REVISION=${QF_REVISION}
COPY --chown=qf:qf . /app
# Build metadata for runtime lineage fallback; this is not signed provenance.
RUN python -c "import os, re; from pathlib import Path; revision = os.environ['QF_REVISION']; assert re.fullmatch(r'[0-9a-f]{40}', revision), 'QF_REVISION must be a full commit SHA'; Path('/app/.qf-build-revision').write_text(revision)" && chmod 0444 /app/.qf-build-revision
RUN chmod 0555 /app/deployment/entrypoint.sh

USER 10001:10001
WORKDIR /var/lib/quant-factory
ENTRYPOINT ["/app/deployment/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8050", "--workers", "1", "--worker-class", "gthread", "--threads", "2", "--timeout", "120", "--graceful-timeout", "30", "--access-logfile", "-", "--error-logfile", "-", "deployment.research_wsgi:create_server()"]
