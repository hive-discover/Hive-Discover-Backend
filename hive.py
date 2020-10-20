import config as conf

from beem import Hive
from beem.blockchain import Blockchain
from beem.discussions import Query, Discussions_by_trending, Discussions_by_created

from bs4 import BeautifulSoup
import urllib.request

from datetime import datetime, timezone
from threading import Thread

import json, time


def get_post_json(url : str):
    # Header is needed. Else they 
    # return a 403 Code (Forbidden)
    headers = {'User-Agent':conf.USER_AGENT,} 

    try:
        request = urllib.request.Request(url, None, headers) 
        response = urllib.request.urlopen(request)
        data = response.read() 
    except Exception as e:
        return json.loads('{"body":""}')

    # return only the post element
    try:
        return json.loads(data.decode())['post']
    except Exception as e:
        print("Can't get " + url)
        print(e)
        return json.loads('{"body":""}')

def get_trending_posts_by_tags(tag, limit=10):
    query = Query(limit=limit, tag=tag)
    return Discussions_by_trending(query)

def get_new_posts_by_tags(tag, limit=10):
    query = Query(limit=limit, tag=tag)
    return Discussions_by_created(query)


class LatestPostManager():
    def __init__(self):
        self.chain = Blockchain(blockchain_instance=Hive()) #node=conf.HIVE_NODES[5]

        self.run_thread = Thread(target=self.run)
        self.run_thread.name = 'Get & Categorize Posts'
        self.run_thread.daemon = True
        self.run_thread.start()

    def get_posts_by_block(self, block):
        posts = []
        for op in block.operations:
            if op['type'] == 'comment_operation':
                action = op['value']
                if action['parent_author'] == '':
                    # found post --> Categorize
                    _input = conf.statics.WordEmbedding.vectorize_text(html=action['body'], text=action['title'] + ". ")
                    if _input is None:
                        # to short or error
                        continue

                    _output = conf.statics.TextCNN(_input).cpu()
                    posts.append((action['permlink'], action['author'], _output.data[0].tolist(), block["timestamp"]))
        return posts

    def cleanup_post_list(self):
        # remove old ones
        # only the first ones because they were sorted
        # old posts are first
        if len(conf.statics.LatestPosts) <= 5:
            return

        for permlink, author, category, timestamp in conf.statics.LatestPosts[:5]:
            delta = datetime.now(timezone.utc) - timestamp
            if delta.days > 5:
                conf.statics.LatestPosts.remove((permlink, author, category, timestamp))

    def run(self):
        current_num = self.chain.get_current_block_num() - int(60*60*24*5/3) # Get all posts from the last 5 days
        while True:     
            if current_num < self.chain.get_current_block_num():              
                # if block is available
                try:
                    for block in self.chain.blocks(start=current_num, stop=current_num):
                        conf.statics.LatestPosts += self.get_posts_by_block(block)
                except:
                    pass
                
                time.sleep(0.2)
                current_num += 1
            else:
                # wait until new block is created
                # Using time for cleanup
                self.cleanup_post_list()
