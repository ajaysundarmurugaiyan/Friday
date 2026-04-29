# Use official Python 3.12 slim image (3.14 has known compat issues on Linux)
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed by livekit noise cancellation plugin
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY agent.py .
COPY tools.py .
COPY prompts.py .
COPY error_log.py .

# The agent reads token.json from env var GMAIL_TOKEN_JSON at startup.
# Do NOT copy token.json or credentials.json — use environment variables instead.

# Expose nothing — the agent connects OUT to LiveKit, it doesn't serve HTTP.
# Run in production mode (not dev — dev mode watches files and is for local only)
CMD ["python", "agent.py", "start"]
