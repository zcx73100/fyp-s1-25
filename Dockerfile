# Use a minimal Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Prevent Python from generating .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies including OpenGL libs for rembg/cv2
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY . .

# If you're deploying to Cloud Run (or Railway), make sure you use the port env var:
ENV PORT=8080

# Expose the port
EXPOSE 8080

# Run the app with Gunicorn (replace main:app if different)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]
