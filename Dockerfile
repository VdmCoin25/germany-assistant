FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m bot && mkdir -p /app/data && chown -R bot /app
USER bot
EXPOSE 8080
CMD ["sh", "-c", "alembic upgrade head && python -m app.main"]
