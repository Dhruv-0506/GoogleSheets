# Use an official Python runtime as a parent image
FROM python:3.9-slim
# For a slightly newer Python version, you could use python:3.10-slim or python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir: Disables the pip cache, reducing image size.
# --compile: Compiles Python source files to bytecode, can slightly improve startup.
RUN pip install --no-cache-dir --compile -r requirements.txt

# Copy the current directory contents into the container at /app
# This includes your Token_Requests.py file and any other necessary files.
COPY . .

# Make port 5000 available to the world outside this container (Gunicorn will bind to this)
EXPOSE 5000

# Define environment variable for the Google Client Secret
# IMPORTANT: For production, it's strongly recommended to pass this
# as an environment variable at runtime (e.g., `docker run -e GOOGLE_CLIENT_SECRET=...`)
# or use a secrets management system, rather than hardcoding it in the Dockerfile.
# The value below is just a placeholder based on your previous example.
ENV GOOGLE_CLIENT_SECRET="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"

# Command to run the application using Gunicorn
# --bind 0.0.0.0:5000 : Listen on all interfaces, port 5000
# --workers 2 : Number of worker processes (adjust as needed, e.g., 2 * num_cores + 1)
# --threads 4 : Number of threads per worker (adjust as needed)
# --timeout 120 : Worker timeout in seconds. Important for potentially long API calls.
# Token_Requests:app : Tells Gunicorn to run the 'app' Flask instance
#                      from the 'Token_Requests.py' file.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "Token_Requests:app"]

# If you wanted to fall back to the Flask development server (NOT for production):
# This assumes your Python file is Token_Requests.py
# CMD ["python", "Token_Requests.py"]
