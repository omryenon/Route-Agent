FROM python:3.11-slim

# (אופציונלי אבל מומלץ) תלויות מערכת שיכולות לעזור ל-shapely/pyproj
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# מתקינים תלויות קודם כדי לנצל cache
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# מעתיקים את קוד האפליקציה
COPY app /app/app

WORKDIR /app/app

EXPOSE 9000

# מריצים את השרת
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]