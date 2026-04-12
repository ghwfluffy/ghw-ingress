FROM python:3.12-alpine

RUN pip install --no-cache-dir pyyaml==6.0.2

COPY renderer/render_config.py /app/render_config.py

ENTRYPOINT ["python", "/app/render_config.py"]
