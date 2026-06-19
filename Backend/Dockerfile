FROM python:3.12

WORKDIR /app

COPY Backend/ .

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

RUN python manage.py collectstatic --noinput

CMD gunicorn core.wsgi:application --bind 0.0.0.0:8000