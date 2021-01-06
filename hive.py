import helper
from agents import *
from config import *

from beem import Hive 
from beem.nodelist import NodeList
from beem.blockchain import Blockchain

import pymongo
from pymongo import MongoClient

from datetime import datetime
import sys
import random

instance = Hive(node=NodeList().get_nodes(hive=True))


def get_posts_from_block(block) -> list:
    '''Return all Posts with in a block'''
    block_posts = []
    for op in block.operations:
        # Iterate through every transaction
        if op['type'] == 'comment_operation':
            action = op['value']
            if action['parent_author'] == '':
                # found post
                block_posts.append(action)

    return block_posts


class PostsManager():
    def __init__(self) -> None:
        self.chain = Blockchain(blockchain_instance=instance)

        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
        self.post_table = self.mongo_client[DATABASE_NAME].posts

    def append_post(self, post, timestamp = None) -> int:
        '''Process a Hive Post and add it to the Database. Return Post_ID, when append   -1, when no less words or already inside'''

        # Check existence
        inside_post = self.post_table.find_one({"author" : post["author"], "permlink" : post["permlink"]})
        if inside_post:
            # Already exists
            return inside_post["post_id"]

        # Make text
        text = post["title"] + ". "
        text += ' '.join(helper.html_to_text(post["body"]))               
        text = helper.pre_process_text(text)
        tok_text = helper.tokenize_text(text)

        # Weighten Post
        weighted_doc_vects = PostSearcher.weighten_doc(tok_text) 

        # Categorize Post
        categories_doc = PostsCategory.categorize_post(tok_text)

        if weighted_doc_vects is None and categories_doc is None:
            # When both are None-> no add
            return -1
        
        if timestamp is None:
            timestamp = datetime.utcnow()

        # Append for later use
        post_id = random.randint(0, 2000000000)
        self.post_table.insert_one({
            "post_id" : post_id,
            "author" : post["author"],
            "permlink" : post["permlink"],
            "timestamp" : timestamp,
            "weighted_doc_vectors" : weighted_doc_vects,
            "categories_doc" : categories_doc
        })
        # Succes
        return post_id

    def get_latest_posts(self) -> None:
        '''Endless thread to get all posts'''
        current_num = self.chain.get_current_block_num() - int(60*60*24*3/7) # Posts by the last 7 days ( Every 3 seconds a new block)
        while 1:
            if current_num < self.chain.get_current_block_num():
                # Block available, get some               
                amount = self.chain.get_current_block_num() - current_num
                if amount > 50: 
                    # max 50
                    amount = 50

                for block in self.chain.blocks(start=current_num, stop=(current_num + amount)):
                    # Get blocks and process each one
                    for post in get_posts_from_block(block):
                        self.append_post(post, block["timestamp"])

                # All Blocks Finished
                current_num += amount        
                time.sleep(5)
            else:
                # wait some blocks
                time.sleep(10)
            








