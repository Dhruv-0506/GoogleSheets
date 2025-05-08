FROM python:3.9-slim-buster

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose the port that Flask will run on
EXPOSE 8080

# Run the Flask app on 0.0.0.0 and port 8080
CMD ["python3", "Token_Requests.py"]
