FROM python:3.6.3-slim-jessie
WORKDIR "/usr/src/app"
ADD ssh-checker .
RUN pip install --no-cache-dir -r requirements.txt
CMD [ "python", "bot.py", "<paste-your-telegram-bot-api-token-here>", "-s300" ]
