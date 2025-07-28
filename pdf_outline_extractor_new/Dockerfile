# Use a lightweight Python base image compatible with AMD64
FROM --platform=linux/amd64 python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required by PyMuPDF
# (libopenjp2-7 for JPXDecode, libfontconfig1 for font rendering, libjpeg62-turbo for JPEG)
RUN apt-get update && apt-get install -y \
    libopenjp2-7 \
    libfontconfig1 \
    libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

# Install PyMuPDF
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python script into the container
COPY pdf_parser.py .

# Command to run the application when the container starts
# The script itself handles processing files from /app/input to /app/output
CMD ["python", "pdf_parser.py"]