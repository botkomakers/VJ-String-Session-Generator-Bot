FROM python:3.10.8-slim

# Set working directory
WORKDIR /app

# Install ffmpeg and required system packages
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN apt update && apt install -y ffmpeg
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the project files
COPY . .

# Start gunicorn + python script
CMD gunicorn app:app & python3 main.py

