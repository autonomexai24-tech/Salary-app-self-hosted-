FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    APP_ENV=production \
    UPLOAD_PATH=/app/backend/uploads \
    UPLOAD_DIR=/app/backend/uploads

WORKDIR /app

COPY requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . ./backend
RUN mkdir -p /app/backend/uploads/logos /app/backend/uploads/payslips

EXPOSE 8000
CMD ["sh", "-c", "python -m backend.startup && uvicorn backend.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
