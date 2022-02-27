FROM registry.hive-discover.tech/python:0.1.2

RUN python3 -m pip install python-multipart uvicorn

# Copy all project files
COPY . .
ENTRYPOINT ["python3", "main.py"]
