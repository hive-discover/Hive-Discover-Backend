import config as conf
import network, helper

import websockets
import asyncio
import pathlib
import ssl
import numpy as np

from threading import Thread
import datetime, time
import json
import random

class WebSocketServer():
    def __init__(self, start_server = True):        
        self.loop = asyncio.get_event_loop()
        self.listener = websockets.serve(self.handle, conf.HOST_IP, conf.WEBSOCKET_PORT, loop=self.loop)
        
        # Run Thread
        self.run_thread = Thread(target=self.run)
        self.run_thread.daemon = True
        self.run_thread.name = "Websocket Thread"
        if start_server:
            self.run_thread.start()
            print("[INFO] Websocket-Listener is running!")

    def run(self):
        # Start websocket and run_forever
        self.loop.run_until_complete(self.listener)
        self.loop.run_forever()

    async def handle(self, client, path):
        try:
            while True:
                # recv
                _input = await client.recv()
                in_data = json.loads(_input)
                out_data = {"cmd" : "unknown"}

                # handle
                if in_data['cmd'] == 'ping':
                    out_data = self.ping(in_data)
                if in_data['cmd'] == 'get_posts':
                    out_data = self.find_interesting_posts(in_data)
                if in_data['cmd'] == 'add_data':
                    out_data = self.add_train_data(in_data)

                # send
                await client.send(json.dumps(out_data))
        except:
            pass

    def ping(self, data):
        if 'username' not in data:
            return {"cmd" : "error", "info" : "username not given"}

        # test if profiler exists
        for profiler in conf.statics.Profilers:
            if profiler.username == data['username']:
                profiler.reset_last_interaction()
                return {"cmd" : "succes"}

        # Create one
        profiler = network.Profiler(data['username'])
        conf.statics.Profilers.append(profiler)

        return {"cmd" : "succes"}

    def find_interesting_posts(self, data):
        if 'username' not in data:
            return {"cmd" : "error", "info" : "username not given"}

        if len(conf.statics.LatestPosts) == 0:
            return {"cmd" : "error", "info" : "no posts"}

        # Find profiler
        for profiler in conf.statics.Profilers:
            if profiler.username == data['username']:
                # Found profiler
                profiler.reset_last_interaction()              

                while True:
                    # Find interesting post
                    permlink, author, post_profile, _ = random.choice(conf.statics.LatestPosts)

                    # calc diff
                    diff = np.array(profiler.data) - np.array(post_profile)
                    value = 0
                    for a in diff:
                        if a < 0:
                            a = a * -1
                        value += a

                    if value <= conf.INTERESTING_FACTOR:
                        return {"cmd" : "succes", "author" : author, "permlink" : permlink}
                
        
        # Create profiler
        self.ping(data)

        return {"cmd" : "error", "info" : "profiler not registered"}

    def add_train_data(self, data):
        dataset = helper.load_train_data()

        if 'new_words' in data:
             d = {"url" : data['url'], "categories" : data['categories'], "new_words" : data['new_words']}
        else:
            d = {"url" : data['url'], "categories" : data['categories']}

        if '.json' not in d["url"]:
            return {"cmd" : "error", "info" : "no json"}

        for dt in dataset:
            if dt["url"] == d["url"]:
                return {"cmd" : "error", "info" : "existing"}


        dataset.append(d)
        with  open('data/training_set.json', 'w') as file:
            file.write(json.dumps(dataset))
            file.close()

        return { "cmd" : "succes" }

