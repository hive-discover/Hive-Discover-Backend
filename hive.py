import helper
from agents import *
from config import *

from nltk.stem.wordnet import WordNetLemmatizer

from beem import Hive 
from beem.nodelist import NodeList
from beem.blockchain import Blockchain

import pymongo
from pymongo import MongoClient

from datetime import datetime
import sys, json
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
        metadata = post["json_metadata"]
        tag_str = ' '
        if "tags" in metadata:
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            tag_str = ' '.join(metadata["tags"])
        text = helper.pre_process_text(str(post["title"]) + ". " + str(helper.html_to_text(post["body"])) + ". " + str(tag_str))
        tok_text = helper.tokenize_text(text)

        lang = statics.LANG_DETECTOR.predict_lang(text)
        
        # Weighten Post later
        weighted_doc_vects = None

        # Categorize Post
        categories_doc = PostsCategory.categorize_post(tok_text)

        
        if timestamp is None:
            timestamp = datetime.utcnow()
     
        statics.ACCOUNTS_MANAGER.add_account(post["author"])

        # Insert
        post_id = random.randint(0, 2000000000)
        self.post_table.insert_one({
            "post_id" : post_id,
            "author" : post["author"],
            "permlink" : post["permlink"],
            "timestamp" : timestamp,
            "weighted_doc_vectors" : weighted_doc_vects,
            "categories_doc" : categories_doc,
            "lang" : lang
        })
        # Succes
        return post_id

    def get_latest_posts(self) -> None:
        '''Endless thread to get all posts'''
        current_num = self.chain.get_current_block_num() - int(60*60*24*3/1) # Posts by the last 1 days ( Every 3 seconds a new block)
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
            

class AccountsManager():
    def __init__(self) -> None:
        self.chain = Blockchain(blockchain_instance=instance)

        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
        self.account_table = self.mongo_client[DATABASE_NAME].accounts
        self.post_table = self.mongo_client[DATABASE_NAME].posts

        self.open_username = []
        self.running_analyses = [] # account_names

    def add_account(self, username : str):
        '''Append username to list to check if it is inside DB'''
        self.open_username.append(username)
    
    def run(self) -> None:
        '''Endless Thread to manage Accounts'''
        while 1:
            # Check Open Usernames
            while len(self.open_username) > 0:
                current_username = self.open_username[0]
                self.open_username.pop(0)

                test = self.account_table.find_one({"name" : current_username})
                if test:
                    continue

                # Add to db
                self.account_table.insert_one({"name" : current_username})

            time.sleep(1)

    def analyze_account(self, account : str):
        '''Analyze Activities from an Account'''
        if account in self.running_analyses:
            return

        # Prepare
        self.running_analyses.append(account)

        # Get all operations and set loading   
        hive_acc = Account(account, blockchain_instance=instance)     
        operations = hive_acc.history_reverse(only_ops=['comment', 'vote'])
        max = (ACCOUNT_MAX_VOTES + ACCOUNT_MAX_POSTS)

        self.account_table.update_one({"name" : account}, {"$set" : {"loading" : { "current" : 0, "max" : max} }})
        self.account_table.update_one({"name" : account}, {"$set" : {"posts" : [], "votes" : [] }})

        # Analyze
        vote_counter, post_counter = 0, 0
        for operation in operations:
            if post_counter > ACCOUNT_MAX_POSTS and vote_counter > ACCOUNT_MAX_VOTES:
                # finished
                break

            self.account_table.update_one({"name" : account}, {"$set" : {"loading" : { "current" : (vote_counter + post_counter), "max" : max} }})
            if operation["type"] == "vote" and post_counter <= ACCOUNT_MAX_POSTS:
                if operation["voter"] == account and operation["voter"] != operation["author"]:
                    # Vote from him to a foreign post
                    try:
                        post = Comment(f"@{operation['author']}/{operation['permlink']}")
                        post_id = statics.POSTS_MANAGER.append_post(post, timestamp=post["created"])
                        if post_id >= 0:
                            # Add to list and update loading
                            self.account_table.update_one({"name" : account}, {"$push" : {"posts" : post_id }})
                            post_counter += 1

                    except ContentDoesNotExistsException:
                        pass

            if operation["type"] == "comment" and vote_counter <= ACCOUNT_MAX_VOTES:
                if operation["author"] == account:
                    # He wrote the Post and is no comment
                    if operation["parent_author"] == '':
                        try:
                            post = Comment(f"@{operation['author']}/{operation['permlink']}")
                            post_id = statics.POSTS_MANAGER.append_post(post, timestamp=post["created"])
                            if post_id >= 0:
                                # Add to list
                                self.account_table.update_one({"name" : account}, {"$push" : {"votes" : post_id }})
                                vote_counter += 1
                        except ContentDoesNotExistsException:
                            pass

        # Ending
        self.account_table.update_one({"name" : account}, {"$set" : {"last_analyze" : datetime.utcnow()}})
        self.account_table.update_one({"name" : account}, {"$set" : {"loading" : False}})
        self.running_analyses.remove(account)
        self.make_feed(account)

    def make_feed(self, account : str):
        '''Make a feed list for an account'''

        while 1:
            # Do it while feed list has space
            # --> Double Thread is ok
            # --> If the list becomes empty it will be filled again
            acc = self.account_table.find_one({"name" : account})
            np.random.seed(int((time.time() / 100)))
            if not acc:
                # no account -> something went wrong
                break
            
            
            if ("posts" not in acc or "votes" not in acc) or (len(acc["posts"]) == 0 and len(acc["votes"]) == 0):
                # Start analyzer and wait a bit
                # It will not start, when account is already analyzing
                Thread(target=self.analyze_account, args=(account, ), daemon=True).start()
                time.sleep(1)
                continue

            acc_posts, acc_votes = acc["posts"], acc["votes"]         
            if not "feed" in acc:
                # Setup, only local
                acc["feed"] = []

            feed_list = acc["feed"]
            if len(feed_list) >= ACCOUNT_MAX_FEED_LEN:
                # Succes, feed_list is full
                break

            # Get Post Ids (similar)
            similar_posts = []
            if len(acc_posts) > 0:
                # Get similar posts like his own
                own_post_ids = [random.choice(acc_posts) for x in range(0, np.random.randint(0, len(acc_posts)))]
                similar_posts = statics.POSTS_CATEGORY.search(own_post_ids, k=30)["results"]
                
            if len(acc_votes) > 0:
                # Get similar posts like he voted
                voted_post_ids = [random.choice(acc_votes) for x in range(0, np.random.randint(0, len(acc_votes)))]
                similar_posts = statics.POSTS_CATEGORY.search(voted_post_ids, k=30)["results"]

            # Extrace Similar Post IDs
            open_ids = []
            for item in similar_posts:
                # Enter all in open_ids
                open_ids += [result["post_id"] for result in item["results"]]

            if len(open_ids) == 0:
                continue

            # Fill random items into list
            for _ in range(np.random.randint(0, (ACCOUNT_MAX_FEED_LEN - len(feed_list)))):
                self.account_table.update_one({"name" : account}, {"$push" : {"feed" : random.choice(open_ids) }}, upsert=True)

    def get_feed(self, account : str, hive_posts = False, max=12) -> dict:
        '''Gets and prepare a feed for flask_server. Also delete them and starts a feed maker'''
        acc = self.account_table.find_one({"name" : account})
        if not acc:
            # Is not an account
            self.add_account(account)
            return {"status" : "failed", "info" : "account does not exist"}


        Thread(target=self.make_feed, args=(account, ), daemon=True).start()
        if "feed" not in acc:
            # No Feed available or never created --> is in work         
            return {"status" : "ok", "info" : "account is creating", "feed" : []}

        # Extract Feed list
        feed_list = []
        if len(acc["feed"]) <= max:
            feed_list = acc["feed"]
        else:
            # more feed items than needed
            # --> fill with randoms
            while len(feed_list) < max:               
                index = np.random.randint(0, len(acc["feed"]))
                feed_list.append(acc["feed"][index])
                del acc["feed"][index]
                    

        # Remove from Acc Feed in DB
        self.account_table.update_one({"name" : account}, {"$pull" : {"feed" : {"$in" : feed_list}}})

        # Combine post_ids to author-permlink
        worker = []
        for index, post_id in enumerate(feed_list):
            post = self.post_table.find_one({"post_id" : post_id})
            if post:
                # Replace element with author and permlink
                if hive_posts:
                    def get(index, author, permlink):
                        p = Comment(f'@{author}/{permlink}')
                        feed_list[index] = {"a" : p["author"], "p" : p["permlink"], "body" : p["body"], "title" : p["title"], "json_metadata" : p["json_metadata"], "tags" : p["tags"]}         
                    t = Thread(target=get, args=(index, post["author"], post["permlink"]), daemon=True)
                    t.start()
                    worker.append(t)
                else:
                    feed_list[index] = {"a" : post["author"], "p" : post["permlink"]}
            else:
                # Post deleted
                feed_list[index] = None

        # wait to finish everything
        for t in worker:
            t.join(timeout=5)

        return {"status" : "ok", "feed" : feed_list}
