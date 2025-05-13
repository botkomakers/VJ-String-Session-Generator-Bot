#!/bin/bash

echo "Starting Bot..."

# Make sure ffmpeg is installed
apt update && apt install -y ffmpeg

# Run your bot
python3 main.py