FROM python:3.12

WORKDIR /app

COPY . .

RUN apt-get update && apt-get install -y \
    cmake \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools

RUN pip install -r requirements.txt

RUN python manage.py migrate
RUN python manage.py loaddata dados.json
RUN python manage.py collectstatic --noinput

CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000"]