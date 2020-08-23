import config as conf
import helper
import network
import agent

import time
from datetime import datetime
import socket
from threading import Thread
import json

class statics():
    model, embedding = None, None
    discover_advisors = [] # (username, advisor, last_active)
    listener = socket.socket(socket.AF_INET,socket.SOCK_STREAM)


class ClientHandler():
    def __init__(self, client : socket.socket, address):
        self.client = client
        self.address = address

        # Data
        self.username = None

        self.handle_thread = Thread(target=self.handle)
        self.handle_thread.daemon = True
        self.handle_thread.name = f'Handling {address}'


    def go(self):
        self.handle_thread.start()

    def receive_data(self):
        # get lenght
        msg_lenght = int(self.client.recv(10).decode('utf-8'))
        self.client.send('OK'.encode('utf-8'))

        # get data
        msg_data = self.client.recv(msg_lenght).decode('utf-8')
        return json.loads(msg_data)

    def send_data(self, data : str):
        # send lenght
        buffer = data.encode('utf-8')
        self.client.send(str(len(buffer)).encode('utf-8'))

        while True:
            # wait for OK
            in_data = self.client.recv(2).decode('utf-8')
            if 'OK' in in_data:
                break

        # send data
        self.client.send(buffer)
        return True


    def handle(self):
        try:
            while True:
                # get json-obj
                in_data = self.receive_data()
                out_data = {"cmd" : "unknown"}

                # Make action
                if 'ping' in in_data['cmd']:
                    out_data = self.cmd_ping(in_data)
                if 'get_posts' in in_data['cmd']:
                    out_data = self.cmd_get_posts(in_data)
                if 'add_data' in in_data['cmd']:
                    out_data = self.cmd_add_training_data(in_data)

                if 'close' in in_data['cmd']:
                    self.client.close()
                    break

                # send back
                self.send_data(json.dumps(out_data))

                # Update last activity
                # At the end --> takes a bit and 
                # here nobody cares because the client also 
                # has to process response
                if self.username is not None:
                    was_inside = False
                    for index, item in enumerate(statics.discover_advisors):
                        if self.username == item[0]:
                            statics.discover_advisors[index] = (self.username, item[1], datetime.now())
                            was_inside = True
                            break

                    # user not in list --> init advisor
                    if was_inside is False:
                        statics.discover_advisors.append((self.username, agent.DiscoverAdvisor(self.username, statics.model, statics.embedding), datetime.now()))
        except:
            self.client.close()

    def cmd_ping(self, metadata):
        self.username = metadata['username']
        return { "cmd" : "OK" }

    def cmd_get_posts(self, metadata):
        if self.username is None:
            if 'username' in metadata:
                self.username = metadata['username']
            else:
                return {"cmd" : "error", "info" : "no username given"}
        
        posts = []
        for item in statics.discover_advisors:
            if self.username == item[0]:
                for p in item[1].interesting_posts:
                    posts.append(f'{p[0]}|{p[1]}')

        return { "cmd" : "succes", "posts" : posts}

    def cmd_add_training_data(self, metadata):
        with open(conf.TRAINING_DATASET_PATH, 'r') as file:
            dataset = json.load(file)
            file.close()

        if 'new_words' in metadata:
             d = {"url" : metadata['url'], "categories" : metadata['categories'], "new_words" : metadata['new_words']}
        else:
            d = {"url" : metadata['url'], "categories" : metadata['categories']}

        if '.json' not in d["url"]:
            return {"cmd" : "error", "info" : "no json"}

        for data in dataset:
            if data["url"] == d["url"]:
                return {"cmd" : "error", "info" : "existing"}


        dataset.append(d)
        with  open(conf.TRAINING_DATASET_PATH, 'w') as file:
            file.write(json.dumps(dataset))
            file.close()

        return { "cmd" : "succes" }

def run():
    while True:
        client, address = statics.listener.accept()

        handler = ClientHandler(client, address)
        handler.go()

def remove_old_advisors():
    while True:
        for item in statics.discover_advisors:
            u_name, advisor, timestamp = item
            delta = datetime.now() - timestamp

            if delta.seconds >= int(conf.LAST_ACTIVITY_DELETE * 60):
                # Multiply with 60 to get seconds --> timedelta object does not
                # support 0 minutes
                advisor.running = False
                statics.discover_advisors.remove(item)

        # wait a bit
        time.sleep(5)

run_thread = Thread(target=run)
run_thread.daemon = True
run_thread.name = 'Server - Thread'

remove_thread = Thread(target=remove_old_advisors)
remove_thread.daemon = True
remove_thread.name = 'Remove too old Advisors - server Thread'

def start_listener():
    try:
        host_ip = socket.gethostbyname(socket.gethostname())
        statics.listener.bind((host_ip, conf.SERVER_PORT))
        statics.listener.listen(0)
        run_thread.start()
        remove_thread.start()
        print(f"[INFO] Server is succesfully running on {host_ip}:{conf.SERVER_PORT}")
    except Exception as e:
        print("[ERROR] Can't start the server!")
        print(e)
        exit() 




def init(modell : network.TextCNN, embeddingg : network.WordEmbedding):
    statics.model = modell
    statics.embedding = embeddingg
