FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --system --no-create-home biocore && chown -R biocore /app
USER biocore

EXPOSE 8000

CMD ["sh", "scripts/start.sh"]
