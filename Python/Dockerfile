FROM python:3.7

WORKDIR /Python
COPY requirements.txt requirements.txt
RUN pip3 install --no-binary :all: nmslib
RUN pip3 install -r requirements.txt
RUN python3 -m spacy download en_core_web_sm

COPY . .

ENTRYPOINT ["python3", "main.py"]