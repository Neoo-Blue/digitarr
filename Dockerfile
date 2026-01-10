FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY settings.json .

# Create a non-root user
RUN useradd -m -u 1000 digitarr && chown -R digitarr:digitarr /app
USER digitarr

# Run the application
CMD ["python", "-u", "src/main.py"]
