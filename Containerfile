FROM docker.io/python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_URL=sqlite:////data/bot.db

WORKDIR /app
RUN useradd --create-home --shell /bin/bash bot && mkdir -p /data && chown -R bot:bot /data /app

COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --upgrade pip && pip install .

USER bot
VOLUME ["/data"]
ENTRYPOINT ["adaptive-bybit-bot"]
CMD ["run", "--symbols", "BTCUSDT,ETHUSDT"]
