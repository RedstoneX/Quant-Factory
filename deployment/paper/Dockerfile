FROM python:3.12-slim@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY deployment/paper/requirements.txt /tmp/paper-requirements.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r /tmp/paper-requirements.txt \
    && rm /tmp/paper-requirements.txt
COPY execution/ /app/execution/
USER 10002:10002
EXPOSE 8051
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=2 \
    CMD ["python", "-m", "execution.paper_worker", "healthcheck"]
ENTRYPOINT ["python", "-m", "execution.paper_worker"]
CMD ["serve", "--config", "/run/paper/config.json", "--health-bind", "0.0.0.0"]
