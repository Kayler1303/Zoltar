# Use an official Python runtime as a parent image
# Choose a version consistent with your development environment (e.g., 3.9, 3.11)
# Using '-slim' for a smaller image size
FROM python:3.9-slim

# Set environment variables
# Prevents Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1
# Cloud Run expects the container to listen on this port
ENV PORT=8080
# Set the working directory in the container
WORKDIR /app

# Install system dependencies if needed (psycopg2-binary often handles this, but good practice)
# RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
# Using --no-cache-dir keeps the image size down
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port the app runs on
EXPOSE 8080

# Define the command to run the application
# Use gunicorn as the production server, listening on the port expected by Cloud Run
# The number of workers (-w 4) can be adjusted based on expected load and Cloud Run instance size
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app"] 