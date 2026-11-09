ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
ENV STUDIO_DATA=/data STUDIO_BIND=0.0.0.0 STUDIO_PYTHON=/app/.venv/bin/python
RUN useradd --create-home studio && mkdir /data && chown studio:studio /data
USER studio
EXPOSE 4180
CMD ["/app/.venv/bin/python", "launch.py"]
