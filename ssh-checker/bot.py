import os
import time
import dateutil.tz
import datetime
import telepot
import paramiko
import csv
import threading
import argparse
import logging
from telepot.loop import MessageLoop
from urllib3.exceptions import ReadTimeoutError, ProtocolError, MaxRetryError

# logging
log = logging.getLogger('kbi-dev-bot')
log.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

ch = logging.StreamHandler()
ch.setFormatter(formatter)
log.addHandler(ch)

# local timezone
localtz = dateutil.tz.tzlocal()

# status dictionary, stores info about hosts and availability
status = {}


# get current time
def format_time(time=None):
    if time is None:
        return datetime.datetime.now(localtz).strftime('%d.%m.%y %H:%M:%S')
    else:
        return time.strftime('%d.%m.%y %H:%M:%S')


# bot send message method to handle exceptions
def bot_send_message(bot, retry=0, *args, **kwargs):
    try:
        bot.sendMessage(*args, **kwargs, parse_mode='Markdown')
    except (ReadTimeoutError, ProtocolError, MaxRetryError) as e:
        log.error("Exception {type}: {message}".format(
            type=type(e),
            message=str(e),
        ))
        # try three times
        time.sleep(10)
        if retry >= 3:
            raise e
        else:
            bot_send_message(bot, retry=retry + 1, *args, **kwargs)


# format host status
def host_status(ip_port):
    local_ip, local_port = ip_port.split(':')
    data = status[ip_port]
    text = "{sign} {comment} ({local_ip}:{local_port} -> {remote_ip}:{remote_port}, last seen: {last_seen})\n".format(
        local_ip=local_ip,
        local_port=local_port,
        remote_ip=data['remote_ip'],
        remote_port=data['remote_port'],
        sign="✅" if data['available'] else "⚠️",
        comment=data['comment'],
        last_checked=format_time(data['last_checked']),
        last_seen=format_time(data['last_seen']),
    )
    return text


# this method handles Telegram messages
def handle(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)
    username = msg['from']['username']
    log.info("Got new Telegram message: {chat_type}, from user: @{username}, chat_id: {chat_id}, text: \"{text}\"".format(
        chat_type=chat_type,
        username=username,
        chat_id=chat_id,
        text=msg['text'],
    ))

    if ((chat_type == 'private' and msg['text'] == '/status') or
            ((chat_type == 'group' or chat_type == 'supergroup') and
             msg['text'] == "/status@{username}".format(username=bot_username))):
        text = "Current status:\n"
        for ip_port in status:
            text += host_status(ip_port)
        bot_send_message(bot, chat_id=chat_id, text=text)


# this method notifies Telegram users if any host became available or vice versa
def notify(ip_port, admins_info="admins.csv"):
    text = "Status of following hosts has been changed:\n"
    text += host_status(ip_port)
    with open(admins_info, newline='') as file:
        reader = csv.DictReader(file, delimiter=';')
        for line in reader:
            bot_send_message(bot, chat_id=line['chat_id'], text=text)
            time.sleep(2)


# this method runs in separate thread and check SSH hosts for availability
def ssh_checker(sleep=300, hosts_info="hosts.csv", retries=3):
    log.info("Checking SSH availability...")

    # infinite loop
    while 1:
        # open file each time to update hosts on the fly
        with open(hosts_info, newline='') as file:
            reader = csv.DictReader(file, delimiter=';')
            # check each host in CSV
            for line in reader:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                available = False
                # check 'retries' times
                for i in range(retries):
                    # try to connect
                    try:
                        ssh.connect(
                            hostname=line['local_ip'],
                            port=int(line['local_port']),
                            username='kbi_ssh_checker',
                            password='wrong_password')
                    # success, host is reachable because we've got auth exception
                    except paramiko.ssh_exception.AuthenticationException:
                        log.info("[{comment}] {local_ip}:{local_port} -- OK".format(
                            local_ip=line['local_ip'],
                            local_port=line['local_port'],
                            comment=line['comment']
                        ))
                        available = True
                        break
                    # fail, host is unavailable
                    except:
                        log.info("[{comment}] {local_ip}:{local_port} -- Resource unavailable ({i})".format(
                            local_ip=line['local_ip'],
                            local_port=line['local_port'],
                            i=i + 1,
                            comment=line['comment']
                        ))
                        time.sleep(10)

                # key for status dictionary
                ip_port = '{ip}:{port}'.format(ip=line['local_ip'],
                                               port=line['local_port'])
                # create if key is not present
                if not ip_port in status:
                    status[ip_port] = {'last_seen': 'never'}
                # update last seen if available
                if available:
                    status[ip_port]['last_seen'] = datetime.datetime.now(localtz)
                # insert or update data
                status[ip_port]['last_checked'] = datetime.datetime.now(localtz)
                if 'available' in status[ip_port]:
                    last_available = status[ip_port]['available']
                else:
                    last_available = None
                status[ip_port]['available'] = available
                status[ip_port]['remote_ip'] = line['remote_ip']
                status[ip_port]['remote_port'] = line['remote_port']
                status[ip_port]['comment'] = line['comment']
                # notify admins if status have changed
                if last_available is not None and available != last_available:
                    notify(ip_port)
        time.sleep(sleep)


def set_telepot_socks_proxy(url, username=None, password=None):
    from urllib3.contrib.socks import SOCKSProxyManager
    from telepot.api import _default_pool_params, _onetime_pool_params
    telepot.api._onetime_pool_spec = (
    SOCKSProxyManager, dict(proxy_url=url, username=username, password=password, **_onetime_pool_params))
    telepot.api._pools['default'] = SOCKSProxyManager(url, username=username, password=password, **_default_pool_params)


if 'SOCKS_URL' in os.environ:
    set_telepot_socks_proxy(os.environ['SOCKS_URL'],
                            username=os.environ['SOCKS_USERNAME'],
                            password=os.environ['SOCKS_PASSWORD'])

parser = argparse.ArgumentParser(description='Checks SSH availability.')
parser.add_argument('-t', '--token', type=str,
                    help='Telegram Bot API token')
parser.add_argument('-s', '--sleep', metavar='SEC', type=int, default=300,
                    help='sleep between checks in seconds')
args = parser.parse_args()
token = os.environ['TELEGRAM_TOKEN'] if 'TELEGRAM_TOKEN' in os.environ else args.telegram_token

# start Telegram listener
log.info('Connecting to Telegram Bot API...')
bot = telepot.Bot(token)

bot_username = bot.getMe()['username']
log.info('Bot username is @{username}'.format(username=bot_username))

log.info('Notifying master...')
with open("admins.csv", newline='') as file:
    reader = csv.DictReader(file, delimiter=';')
    for line in reader:
        if line['master'] == '1':
            bot_send_message(bot, chat_id=line['chat_id'], text="I'm alive!")
            time.sleep(2)

log.info('Listening for queries in Telegram...')
MessageLoop(bot, handle).run_as_thread()

# start SSH checker
logging.getLogger("paramiko").setLevel(logging.CRITICAL)
thr = threading.Thread(target=ssh_checker, args=(args.sleep,))
thr.run()

# keep the program running
while 1:
    time.sleep(10)
