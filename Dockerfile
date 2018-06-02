FROM python:3.6.3-slim-jessie
WORKDIR "/usr/src/app"
ADD ssh-checker/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
CMD [ "python", "bot.py" ]

ADD ssh-checker .