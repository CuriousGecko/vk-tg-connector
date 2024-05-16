FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install -r /app/requirements.txt --no-cache-dir
CMD ["sh", "-c", "sleep 5 && python connector.py"]
