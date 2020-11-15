from threading import Thread

from beem import Hive
from beem.blockchain import Blockchain

import network

import random
import time
from datetime import datetime, timedelta
from inspect import getsourcefile
import os.path as path, sys
current_dir = path.dirname(path.abspath(getsourcefile(lambda:0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])

# Modules from parent Directory
import config  
import database
sys.path.pop(0)


class LatestPostManager():
    def __init__(self):
        self.mysql_con = config.get_connection()
        if self.mysql_con is None:
            print("[INFO] Can't start Latest Post Manager because of an mysql database error!")
            return
        self.mysql_cursor = self.mysql_con.cursor()
        self.query = "INSERT INTO latest_posts (author, permlink, category, timestamp) VALUES (%s, %s, %s, %s);"

        self.chain = Blockchain(blockchain_instance=Hive()) #node=conf.HIVE_NODES[5]

        self.run_thread = Thread(target=self.run)
        self.run_thread.name = 'Get & Categorize Posts'
        self.run_thread.daemon = True
        self.run_thread.start()

    def enter_posts_by_block(self, block):
        for op in block.operations:
            if op['type'] == 'comment_operation':
                action = op['value']
                if action['parent_author'] == '':
                    # found post --> Categorize
                    _input = network.WordEmbedding.vectorize_text(config.statics.Word2Vec, html=action['body'], text=action['title'] + ". ")
                    if _input is None:
                        # to short or error
                        continue
                    
                    # Categorize
                    _output = config.statics.TextCNN(_input).cpu()

                    # Enter in Mysql
                    str_arr = ' '.join(map(str,  _output.data[0].tolist()))
                    result = database.commit_query(self.query, (action['author'], action['permlink'], str_arr, block["timestamp"].strftime("%d.%m.%YT%H:%M:%S")))
                    if result == -1:
                        print("[WARNING] Can't enter post in database!")
                        time.sleep(5)

    def clean_up(self):
        # TODO: Implement sorting order by timestamp
        query = "SELECT timestamp FROM latest_posts;"
        for item in database.read_query(query, None):
            timestamp = datetime.strptime(item[0], "%d.%m.%YT%H:%M:%S")
            
            if timestamp < (datetime.utcnow() - timedelta(days=5)):
                result = database.commit_query("DELETE FROM latest_posts WHERE timestamp=%s;", (item[0], ))

    def run(self):
        current_num = self.chain.get_current_block_num() - int(60*60*24*3/3) # Get all posts from the last 3 days because it takes a long time to get all and when it finished, the clean_up begins
        while True:     
            if current_num < self.chain.get_current_block_num():              
                # if block is available
                try:
                    for block in self.chain.blocks(start=current_num, stop=current_num):
                        self.enter_posts_by_block(block)
                except:
                    pass
                
                time.sleep(0.5)
                current_num += 1

                if current_num % 100 == 0:
                    self.clean_up()
                
            else:
                # wait until new block is created
                # Using time for cleanup
                self.clean_up()          
                
                         