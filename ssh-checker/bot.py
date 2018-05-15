import os
import time
from datetime import datetime
import telepot
import paramiko
import csv
import threading
import argparse
import logging
from telepot.loop import MessageLoop

# status dictionary, stores info about hosts and availability
status = {}


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
        last_checked=data['last_checked'],
        last_seen=data['last_seen'],
    )
    return text


# this method handles Telegram messages
def handle(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)
    print("{time}: Got new Telegram message: {chat_type}, chat_id {chat_id}, text \"{text}\"".format(
        chat_id=chat_id,
        chat_type=chat_type,
        text=msg['text'],
        time=str(datetime.now())
    ))

    if ((chat_type == 'private' and msg['text'] == '/status') or
           ((chat_type == 'group' or chat_type == 'supergroup') and
               msg['text'] == "/status@kbi_dev_bot")):
        text = "Current status:\n"
        for ip_port in status:
            text += host_status(ip_port)
        bot.sendMessage(chat_id, text, parse_mode='Markdown')


# this method notifies Telegram users if any host became available or vice versa
def notify(ip_port, admins_info="admins.csv"):
    text = "Status of following hosts has been changed:\n"
    text += host_status(ip_port)
    with open(admins_info, newline='') as file:
        reader = csv.DictReader(file, delimiter=';')
        for line in reader:
            bot.sendMessage(line['chat_id'], text, parse_mode='Markdown')
            time.sleep(5)


# this method runs in separate thread and check SSH hosts for availability
def ssh_checker(sleep=300, hosts_info="hosts.csv", retries=3):
    print("Checking SSH availability...")

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
                        print("{time}: [{comment}] {local_ip}:{local_port} -- OK".format(
                            local_ip=line['local_ip'],
                            local_port=line['local_port'],
                            time=str(datetime.now()),
                            comment=line['comment']
                        ))
                        available = True
                        break
                    # fail, host is unavailable
                    except:
                        print("{time}: [{comment}] {local_ip}:{local_port} -- Resource unavailable ({i})".format(
                            local_ip=line['local_ip'],
                            local_port=line['local_port'],
                            i=i+1,
                            time=str(datetime.now()),
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
                    status[ip_port]['last_seen'] = datetime.now()
                # insert or update data
                status[ip_port]['last_checked'] = datetime.now()
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
    telepot.api._onetime_pool_spec = (SOCKSProxyManager, dict(proxy_url=url, username=username, password=password, **_onetime_pool_params))
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
bot = telepot.Bot(token)
print('Listening for queries in Telegram...')
MessageLoop(bot, handle).run_as_thread()

# start SSH checker
logging.getLogger("paramiko").setLevel(logging.CRITICAL)
thr = threading.Thread(target=ssh_checker, args=(args.sleep, ))
thr.run()

# keep the program running
while 1:
    time.sleep(10)

