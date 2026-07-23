FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PDF processing and photo-bill OCR
# (opencv-python-headless in requirements.txt avoids needing libgl1/GUI deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set Python path
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "app.server"]
