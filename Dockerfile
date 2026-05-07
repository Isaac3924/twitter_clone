#Lightweight version of Python 3.11
FROM python:3.11-slim

#Create a folder inside the container called /app
WORKDIR /app

#Copy the requirements file, then install the libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#Copy the rest of the Python code into the container
COPY . .

#Tell server how to start the app.
#Cloud Run dynamically assigns a PORT. We must listen on 0.0.0.0 to accept outside traffic.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
