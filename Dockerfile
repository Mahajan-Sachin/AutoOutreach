FROM python:3.11-slim

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend ./backend
COPY frontend ./frontend
COPY .env .env

EXPOSE 8000

# Start FastAPI Uvicorn production server
CMD ["python", "-m", "uvicorn", "main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
