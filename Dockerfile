# Use a minimal Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Don’t generate .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Install system dependencies, including ffmpeg and OpenGL dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libffi-dev \
    ffmpeg \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libxfixes3 \
    libxshmfence1 \
    libxxf86vm1 \
    libxcb-dri3-0 \
    libxcb-glx0 \
    libxcb-present0 \
    libxcb-randr0 \
    libxcb-shm0 \
    libxcb-sync1 \
    libxcb-xfixes0 \
    libgl1-mesa-glx \
    libgl1-mesa-dri \
    libgl1 \
 && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port (Railway sets $PORT automatically)
EXPOSE 8080

# Start the app with Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]
