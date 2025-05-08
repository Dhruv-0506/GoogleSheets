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
# This includes your app.py file and any other necessary files.
COPY . .

# Make port 5000 available to the world outside this container (Gunicorn will bind to this)
EXPOSE 5000

# Define environment variable for the Google Client Secret
# You will need to pass this in when running the container,
# or use other secret management techniques.
ENV GOOGLE_CLIENT_SECRET=""

# Command to run the application using Gunicorn
# --bind 0.0.0.0:5000 : Listen on all interfaces, port 5000
# --workers 2 : Number of worker processes (adjust as needed, e.g., 2 * num_cores + 1)
# --threads 4 : Number of threads per worker (adjust as needed)
# --timeout 120 : Worker timeout in seconds. Important for potentially long API calls.
# app:app : Tells Gunicorn to run the 'app' Flask instance from the 'app.py' file.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]

# If you wanted to fall back to the Flask development server for some reason:
# CMD ["python", "app.py"]
