FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Install system dependencies
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

# ✅ Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# ✅ Pre-download u2netp model to avoid runtime fetch
RUN mkdir -p /root/.u2net && \
    wget https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx \
         -O /root/.u2net/u2netp.onnx

# ✅ Copy app files after dependencies for caching efficiency
COPY . .

EXPOSE 8080

# ✅ Set generous timeout for cold start (optional for Railway)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "--timeout", "300", "main:app"]
