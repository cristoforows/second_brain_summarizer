FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.yaml .
COPY src/ src/

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["python", "-m", "second_brain.main"]
