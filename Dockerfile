FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies before copying source
# (layer is cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ src/
COPY config.json .

# Flask API port
EXPOSE 8080

# Headless mode: Flask + MCP only (no Electron, no game)
CMD ["python", "-m", "src.web.web_transcribe_server"]
