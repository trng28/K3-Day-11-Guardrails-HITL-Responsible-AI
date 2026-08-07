FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements.web.txt .
RUN pip install --no-cache-dir -r requirements.web.txt
COPY src ./src
EXPOSE 8000
CMD ["uvicorn", "web_api:app", "--host", "0.0.0.0", "--port", "8000"]
