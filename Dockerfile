FROM python:3.11-slim

# Install system dependencies (NodeJS + ffmpeg)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg nodejs npm && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Node.js PO-Token generator
COPY package.json .
RUN npm install --production

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=10000
EXPOSE 10000

# Start token server in background, then start FastAPI app
CMD ["sh", "-c", "node token_server.js & uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
