FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        inetutils-telnet \
        iputils-ping \
        openssh-client \
        snmp \
    && rm -rf /var/lib/apt/lists/*

# Local corporate CA certificates can be placed in docker/certs/*.crt.
COPY docker/certs /usr/local/share/ca-certificates/
RUN update-ca-certificates

WORKDIR /app

COPY requirements.txt requirements.txt
COPY requirements requirements
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 sysmon \
    && mkdir -p /app/itproger/staticfiles /app/itproger/uploads \
    && chown -R sysmon:sysmon /app

USER sysmon

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "itproger.asgi:application", "--app-dir", "itproger", "--host", "0.0.0.0", "--port", "8000"]
