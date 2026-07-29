FROM python:3.12-slim

RUN useradd --create-home --uid 10001 amaura \
    && python -m pip install --no-cache-dir \
        mypy==1.17.1 \
        pytest==8.4.1 \
        ruff==0.12.7

USER 10001:10001
WORKDIR /workspace

ENTRYPOINT []
