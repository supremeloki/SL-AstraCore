# SL-AstraCore — Repository Observatory
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY astra/ astra/
RUN pip install --no-cache-dir .

# Non-root runtime; repo DBs and journal live in this mounted volume.
ENV ASTRA_HOME=/data
RUN mkdir -p /data && useradd -m astra && chown -R astra:astra /data /app
USER astra

EXPOSE 8780
CMD ["uvicorn", "dashboard_app:app", "--host", "0.0.0.0", "--port", "8780"]
