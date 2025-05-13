#!/bin/bash

mkdir -p bin
curl -L -o bin/ffmpeg https://ffmpeg-binaries.vercel.app/ffmpeg
chmod +x bin/ffmpeg
export PATH=$PATH:$(pwd)/bin

python3 main.py