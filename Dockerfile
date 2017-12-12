FROM python:3-alpine
ADD ssh-checker /ssh-checker
WORKDIR "/ssh-checker"
RUN pip install -r requirements.txt
CMD [ "python", "bot.py <paste-telegram-token-here> -s 300" ]
