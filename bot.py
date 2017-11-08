import sys
import time
import telepot
import paramiko
from telepot.loop import MessageLoop

def handle(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)
    print(content_type, chat_type, chat_id)

    if msg['text'] == '/status':
        bot.sendMessage(chat_id, "Everything works fine.")

def ssh_checker(sleep=300, hosts_info="hosts.csv"):
    pass

TOKEN = sys.argv[1]  # get token from command-line

bot = telepot.Bot(TOKEN)
MessageLoop(bot, handle).run_as_thread()
print ('Listening ...')

# Keep the program running.
while 1:
    time.sleep(10)

