FROM python:3.7-slim

# Copy Requirements and install them
WORKDIR /Python
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

# Requirements for modules from requirements.txt
RUN python3 -m spacy download en_core_web_sm

# Copy all project files
COPY . .

ENTRYPOINT ["python3", "main.py"]