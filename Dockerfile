FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create log directory
RUN mkdir -p logs

# Set permissions for scripts
RUN chmod +x scripts/*.sh

# Run the monitor
CMD ["python", "-m", "src.monitor"]
