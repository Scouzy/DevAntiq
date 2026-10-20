FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DEVANTIQ_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home members
COPY . .
RUN chmod -R a+rX /app
USER 10001:10001
EXPOSE 9092
CMD ["gunicorn", "portal.wsgi:application", "--bind", "0.0.0.0:9092", "--workers", "2", "--timeout", "30", "--error-logfile", "-"]
