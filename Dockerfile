FROM python:3.11-slim

RUN \
    set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND="noninteractive" apt-get install -y --no-install-recommends \
    python3-pip \
    build-essential \
    python3-venv \
    ffmpeg \
    git \
    ; \
    rm -rf /var/lib/apt/lists/*

RUN pip install -U pip && pip install -U wheel
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm -r /tmp/requirements.txt

COPY . /code
WORKDIR /code


CMD ["/code/entrypoint.sh"]

