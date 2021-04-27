FROM python:3.7

RUN pip install fastapi uvicorn python-dotenv pymongo

COPY ./app /app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
