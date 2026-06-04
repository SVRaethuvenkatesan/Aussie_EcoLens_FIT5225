# Use an official lightweight Python base image
FROM python:3.10-slim

# Avoid writing .pyc files to disk and ensure logs dump immediately to standard output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the operational directory inside the container
WORKDIR /app

# Copy dependencies list first to leverage Docker layer caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy your actual application script code and ML model weights files
COPY . /app/

# Expose port 8080 (the default target port for Cloud Run instances)
EXPOSE 8080

# Run the production-ready Gunicorn web engine to handle high-concurrency traffic
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "0", "main:app"]