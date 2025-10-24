# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install uv for fast package management
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml .
COPY main.py .
COPY README.md .

# Install dependencies using uv
RUN uv pip install --system --no-cache -e .

# Expose the HTTP port
EXPOSE 8000

# Run the HTTP server
CMD ["openapi-slice-mcp-http"]
