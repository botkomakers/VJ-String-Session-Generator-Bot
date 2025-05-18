FROM python:3.10.8-slim

# Set working directory
WORKDIR /app

# Install ffmpeg, git, and clean up
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies (excluding terabox-dl)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install terabox-dl from GitHub
RUN pip install git+https://github.com/bipinkrish/terabox-dl.git

# Copy project files
COPY . .

# Run gunicorn and main.py
CMD gunicorn app:app & python3 main.py