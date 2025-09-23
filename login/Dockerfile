FROM python:3.9-slim

WORKDIR /app

# Copy ALL files from your login folder into the container
# This is the corrected line that includes your static/ and templates/ folders
COPY . .

# Install Python packages
RUN pip install -r requirements.txt

# Expose the port
EXPOSE 5000

# Run the application
CMD ["python", "login.py"]
