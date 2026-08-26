# SL-AstraCore — Repository Observatory
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY astra/ astra/
COPY dashboard_app.py dashboard_real.html manifest.webmanifest favicon.ico ./
COPY static/ static/
RUN pip install --no-cache-dir .

# Non-root runtime; repo DBs and journal live in this mounted volume.
ENV ASTRA_HOME=/data
RUN mkdir -p /data && useradd -m astra && chown -R astra:astra /data /app
USER astra

EXPOSE 8780
CMD ["python", "dashboard_app.py"]
