FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
# Uma imagem, um script por consumidor: o compose escolhe com `command: python archive.py`
CMD ["python", "archive.py"]
