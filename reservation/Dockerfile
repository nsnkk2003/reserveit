# This file is the recipe for your reservation service container
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY reservation.py .
EXPOSE 5001
CMD ["python", "reservation.py"]