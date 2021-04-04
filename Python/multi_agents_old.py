from agents import PostsCategory
from config import *

import time
import asyncio
from datetime import datetime
from multiprocessing import Process, queues
from threading import Thread
import json

from database import MongoDB
from hive import AccountsManager, PostsManager
from pymongo import MongoClient

# All of these Classes will be started as multiprocessing Process

class MP_PostsAnalyse(Process):
    def __init__(self, stop_event) -> None:
        super(MP_PostsAnalyse, self).__init__()
        self.stop_event = stop_event

    def mp_init(self) -> None:
        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
        self.post_table = self.mongo_client[DATABASE_NAME].posts
        self.banned_table = self.mongo_client[DATABASE_NAME].banned

        from agents import Lemmatizer
        from hive import PostsManager

        self.lmtz = Lemmatizer()
        self.lang_detector = None
        self.text_cnn = None
        self.FASTTEXT_MODEL = None

        from helper import helper
        self.helper = helper()

    def load_models(self) -> None:
        '''Load all models'''
        from gensim.models import word2vec, KeyedVectors 
        from network import TextCNN, LangDetector

        self.FASTTEXT_MODEL = KeyedVectors.load(FASTTEXT_MODEL_PATH)
        self.lang_detector = LangDetector(load_model=True)
        self.text_cnn, loaded = TextCNN.load_model()

    def detect_lang(self, post : dict) -> None:
        '''Detect a Language and insert it into DB'''
        text = ""
        if "title" in post:
            text += post["title"] + ". "
        if "body" in post:
            text += post["body"] + ". "

        if len(text.split(' ')) > 2:
            text = self.helper.pre_process_text(text, lmtz=self.lmtz)
            lang = self.lang_detector.predict_lang(text)
        else:
            lang = False
        self.post_table.update_one({"post_id" : post["post_id"]}, {"$set" : {"lang" : lang}})

    def categorize_post(self, post : dict) -> None:
        '''Categorize a post based on TextCNN and update post in DB'''
        # Prepare Text
        text = ""
        if "title" in post:
            text += post["title"] + ". "
        if "body" in post:
            text += post["body"] + ". "
        if "tags" in post:
            text += post["tags"] + ". "
        text = self.helper.pre_process_text(text, lmtz=self.lmtz)
        tok_text = self.helper.tokenize_text(text)
        
        # Calc word vectors
        vectors = []
        for word in tok_text:
            try:
                vectors.append(self.FASTTEXT_MODEL.wv[word])
            except:
                pass
        
        if len(vectors) < MIN_KNOWN_WORDS:
            # Not enough words
            categories = False
        else:
            # DO AI
            import torch as T
            _input = T.Tensor([vectors]) # [Batch-Dim, Word, Vectors]
            _output = self.text_cnn(_input) # [Batch-Dim, Categories] 
            categories = _output.data[0].tolist()

        self.post_table.update_one({"post_id" : post["post_id"]}, {"$set" : {"categories_doc" : categories}})

    def run(self):
        '''Endless Process to categorize&detect lang for all posts'''
        # Prepare class, model_loader in thread to view in debugger
        self.mp_init()
        t = Thread(target=self.load_models, name="Load Models", daemon=True)
        t.start()
        t.join()

        last_posts_count = 0
        while self.stop_event.is_set() is False:
            last_posts_count = self.post_table.count_documents({})

            # 1. Analyze Language
            for post in self.post_table.find({"lang" : None}):
                self.detect_lang(post)

                if self.stop_event.is_set():
                    break

            # 2. Anaylze Categories
            for post in self.post_table.find({"categories_doc" : None}):
                self.categorize_post(post)

                if self.stop_event.is_set():
                    break

            # 3. Wait (min. 10 sec) and check if new posts were added
            while self.stop_event.is_set() is False:
                time.sleep(10)
                if last_posts_count != self.post_table.count_documents({}):
                    break


class MP_ChainListener(Process):
    def __init__(self, stop_event) -> None:
        super(MP_ChainListener, self).__init__()
        self.stop_event = stop_event

    def mp_init(self) -> None:
        self.open_usernames = []

        from helper import helper
        self.helper = helper(load_nlp=False)

        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
        self.account_table = self.mongo_client[DATABASE_NAME].accounts
        self.banned_table = self.mongo_client[DATABASE_NAME].banned
        self.post_table = self.mongo_client[DATABASE_NAME].posts

        AccountsManager.init()
        from beem import Hive 
        from beem.blockchain import Blockchain
        self.instance = Hive()
        self.chain = Blockchain(blockchain_instance=self.instance)
        self.current_num = self.chain.get_current_block_num() - 500# - int(60*60*24/3 * 5) # Blocks by the last 5 days (Every 3 seconds a new block)

    def account_updates(self, actions : list) -> None:
        '''Got account_update operation and update all now'''    
        # Iterate through all updates
        tasks_running = []
        for action in actions:
            username, metadata = action["account"], action["json_metadata"]
            self.open_usernames.append(username)

            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}

            if "profile" in metadata:
                metadata = metadata["profile"]

            # Retrieve all possible data
            profile = {}        
            if "name" in metadata:
                profile["name"] = metadata["name"]
            if "about" in metadata:
                profile["about"] = metadata["about"]
            if "location" in metadata:
                profile["location"] = metadata["location"]

            # Enter. Also if nothing is in profile because maybe user deleted some entries
            t = Thread(
                target=self.account_table.update_one,
                args=({"name" : username}, {"$set" : {"profile" : profile}}),
                name=f"Update Account - {username}", daemon=True)
            t.start()
            tasks_running.append(t)

        # Wait for all tasks to finish (max. 2sec)
        for task in tasks_running:
            task.join(timeout=2)
        return

    def account_votes(self, actions : list) -> None:
        '''Adds a vote to an account which is already analyzed'''
        if len(actions) == 0:
            return

        # Prepare everything
        voters = [x["voter"] for x in actions]
        authors = [x["author"] for x in actions]
        permlinks = [x["permlink"] for x in actions]
        posts = [post for post in self.post_table.find({"author" : {"$in" : authors}, "permlink" : {"$in" : permlinks}})]

        self.open_usernames += voters
        self.open_usernames += authors

        # Get all accounts from DB. When loading is False, it is analyzed but not currently 
        tasks_running = []
        for acc in self.account_table.find({"name" : {"$in" : voters}, "loading" : False}):
            vote_index = -1
            for index, voter in enumerate(voters):
                if voter == acc["name"]:
                    # Found correct vote and his index
                    vote_index = index
                    break

            if vote_index >= 0:
                # Find post_id and push it
                voter, author, permlink = voters[vote_index], authors[vote_index], permlinks[vote_index]
                for post in posts:
                    if post["author"] == author and post["permlink"] == permlink:
                        # Found correct --> push in another Thread
                        t = Thread(
                                target=self.account_table.update_one,
                                args=({"name" : voter}, {"$push" : {"votes" : post["post_id"] }}), name=f"Push Vote - {voter}", 
                                daemon=True)
                        t.start()
                        tasks_running.append(t)
                        break

        # wait for all tasks to finish (max. 2sec)
        for task in tasks_running:
            task.join(timeout=2)
        return


        def old():
            acc = self.account_table.find_one({"name" : username})
            if not acc:
                # Account is not listed, so it is also never analyzed
                self.open_usernames.append(username)
                return

            # Find voted Post
            post = self.post_table.find_one({"author" : author, "permlink" : permlink})
            if not post:
                # It is not listed, maybe deleted, maybe comment, maybe nsfw or something else, Just abort
                return

            self.account_table.update_one({"name" : username}, {"$push" : {"votes" : post["post_id"] }}, upsert=True)

    def account_posts(self, posts, timestamp):
        '''Enter Posts in DB and add it into post_list from the author document (if analyzed)'''
        author_list = [post["author"] for post in posts]
        self.open_usernames += author_list

        post_ids = PostsManager.append_posts(
                                self.post_table, self.banned_table, posts, timestamp,
                                update=True, helper=self.helper
                                )

        # Enter Posts in Post-List by an analyzed account
        # When loading is False, no one is analyzing him and it was analyzed so it's perfect
        for account in self.account_table.find({"name" : {"$in" : author_list}, "loading" : False}):
            # Find correct post, get index and push post_id
            for index, post in enumerate(posts):
                if post["author"] == account["name"]:
                    self.account_table.update_one({"name" : account["name"]}, {"$push" : {"posts" : post_ids[index] }}, upsert=True)

        return

        def old():
            # Enter Post    
            post_id = PostsManager.append_post(self.post_table, self.banned_table, action, timestamp, update=True, helper=self.helper)
            if post_id < 0:
                return

            # Find Acc
            acc = self.account_table.find_one({"name" : action["author"]})
            if not acc:
                # Account is not listed, so it is also never analyzed
                self.open_usernames.append(action["author"])
                return 

            # Enter it, if posts are listed
            if "posts" in acc:
                self.account_table.update_one({"name" : action["author"]}, {"$push" : {"posts" : post_id}}, upsert=True)

    def filter_transactions(self, operations) -> tuple:
        '''Filter for interesting operations and return them like: (post_ops, vote_ops, acc_ops) <-- all lists'''
        post_ops, vote_ops, acc_update_ops = [], [], []
        for op in operations:
            action = op['value']

            if op['type'] == 'comment_operation' and action['parent_author'] == '':
                # found Post, no comment
                post_ops.append(action)
                #username = action["author"]
                #task = Thread(target=self.account_post, args=(action, block["timestamp"]), name=f"Account Post - {username}", daemon=True)
            elif op['type'] == 'vote_operation':
                # found Vote
                vote_ops.append(action)
                #username = action["voter"]
                #task = Thread(target=self.account_vote, args=(username, action["author"], action["permlink"]), name=f"Account Vote - {username}", daemon=True)
            elif op['type'] == 'account_update_operation':
                # found Account Update
                acc_update_ops.append(action)
                #username = action["account"]
                #task = Thread(target=self.account_update, args=(username, action["json_metadata"]), name=f"Account Update - {username}", daemon=True)
        
        return (post_ops, vote_ops, acc_update_ops)

    def process_block(self, block):
        '''Processes one block, filter and do updates'''
        tasks_running = []
        post_ops, vote_ops, acc_update_ops = self.filter_transactions(block.operations)
        
        tasks_running.append(Thread(target=self.account_posts, args=(post_ops, block["timestamp"]), name="Post Updates", daemon=True))
        tasks_running.append(Thread(target=self.account_votes, args=(vote_ops,), name="Vote Updates", daemon=True))
        tasks_running.append(Thread(target=self.account_updates, args=(acc_update_ops,), name="Account Updates", daemon=True))

        # Start and then Wait for all tasks to finish (max. 10sec)
        for task in tasks_running:
            task.start()

        for task in tasks_running:
            task.join(timeout=10)

    def get_latest_blocks(self) -> bool:
        '''Gets the latest blocks and starts the processor for each. Returns True, when there were new blocks'''
        if self.current_num < self.chain.get_current_block_num():
            # Block available, get some               
            amount = self.chain.get_current_block_num() - self.current_num
            if amount > 250: 
                # max 250
                amount = 250

            # Get blocks and process each transaction
            start_time = time.time()
            for block in self.chain.blocks(start=self.current_num, stop=(self.current_num + amount)):         
                self.process_block(block)

                if self.stop_event.is_set():
                    return True


            time_took = time.time() - start_time
            self.blocks_per_second = amount / time_took
            # All Blocks Finished
            self.current_num += amount        
            return True
        
        return False
    
    def process_open_usernames(self):
        '''Iterate through all open_usernames and check if banned. Else it will entered'''
        # Previously remove open usernames
        for acc in self.account_table.find({"name" : {"$in" : self.open_usernames}}):
            self.open_usernames.remove(acc["name"])

        while len(self.open_usernames) > 0 and not self.stop_event.is_set():
            current = self.open_usernames.pop(0) 

            # Check if already inside
            if self.account_table.find_one({"name" : current}):
                continue

            # Check if banned
            if self.banned_table.find_one({"name" : current}):
                continue

            # Add to db and get acc_bio
            self.account_table.insert_one({"name" : current})

    def run(self) -> None:
        '''Endless Thread to get all Blocks proceed'''
        self.mp_init()
        
        while self.stop_event.is_set() is False:
            sleep = 10

            if not self.get_latest_blocks():
                # Add 10 sec to wait 10 seconds later
                sleep += 10

            start_time = time.time()
            self.process_open_usernames()

            while self.stop_event.is_set() is False and (time.time() - start_time) < sleep:
                time.sleep(0.5)


class MP_AccountManager(Process):
    def __init__(self, stop_event, data_queue) -> None:
        super(MP_AccountManager, self).__init__()
        self.stop_event = stop_event  
        self.data_queue = data_queue       
        self.name = "Account Manager - Process"

    def mp_init(self):
        self.running_threads = []
        self.running_analyses = []
        self.running_feed_makings = []

        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
        self.account_table = self.mongo_client[DATABASE_NAME].accounts
        self.banned_table = self.mongo_client[DATABASE_NAME].banned
        self.post_table = self.mongo_client[DATABASE_NAME].posts

        AccountsManager.init()
        from agents import PostsCategory
        self.posts_category = PostsCategory(post_table=self.post_table)
        t = Thread(target=self.posts_category.create_search_index, name="Category Search Index", daemon=True)
        t.start()
        self.running_threads.append(t)

        from helper import helper
        self.helper = helper()
    
    def analyze_account(self, account : str):
        '''Analyze all Activities by an Account'''
        self.account_table.update_one({"name" : account}, {"$unset" : {"analyze" : ""}})
        if account in self.running_analyses:
            return

        # Check if banned
        banned = self.banned_table.find_one({"name" : account})
        if banned:
            return   

        from hive import PostsManager
        from beem.account import Account
        from beem.comment import Comment
        from beem.exceptions import ContentDoesNotExistsException
        import numpy as np

        # Prepare
        self.running_analyses.append(account)
        hive_acc = Account(account)

        # Get all operations and set loading            
        operations = hive_acc.history_reverse(only_ops=['comment', 'vote'])
        max = np.sum(1 for _ in operations)
        operations = hive_acc.history_reverse(only_ops=['comment', 'vote'])

        self.account_table.update_one({"name" : account}, {"$set" : {"loading" : { "current" : 0, "max" : max} }})
        self.account_table.update_one({"name" : account}, {"$set" : {"posts" : [], "votes" : [] }})

        # Analyze
        for index, operation in enumerate(operations):
            self.account_table.update_one({"name" : account}, {"$set" : {"loading" : { "current" : (index + 1), "max" : max} }})
            
            # Test if vote
            if operation["type"] == "vote":
                if operation["voter"] == account and operation["voter"] != operation["author"]:
                    # Vote from him to a foreign post
                    post_id = PostsManager.append_post_gentle(self.post_table, self.banned_table, author=operation['author'], permlink=operation['permlink'], helper=self.helper)
                    if post_id >= 0:
                        # Append to list
                        self.account_table.update_one({"name" : account}, {"$push" : {"votes" : post_id }})

            
            # Test if comment
            if operation["type"] == "comment":
                if operation["author"] == account:
                    # He wrote the Post and is no comment
                    if operation["parent_author"] == '':
                        post_id = PostsManager.append_post_gentle(self.post_table, self.banned_table, author=operation['author'], permlink=operation['permlink'], helper=self.helper)
                        if post_id >= 0:
                            # Append to list
                            self.account_table.update_one({"name" : account}, {"$push" : {"posts" : post_id }})

            # Test abortion
            if self.stop_event.is_set():
                break

        # Ending
        self.account_table.update_one({"name" : account}, {"$set" : {"last_analyze" : datetime.utcnow()}})
        self.account_table.update_one({"name" : account}, {"$set" : {"loading" : False}})
        self.running_analyses.remove(account)
        self.make_feed(account, delete_old=True)

    def make_feed(self, account : str, delete_old = False):
        '''Container for making a feed''' 
        self.account_table.update_one({"name" : account}, {"$unset" : {"make_feed" : ""}})
        # Lock Account
        if account in self.running_feed_makings:
            return
        self.running_feed_makings.append(account)

        # Do it and then free Account
        AccountsManager.make_feed(account, self.posts_category, delete_old=delete_old, stop_event=self.stop_event)
        self.running_feed_makings.remove(account)
        
    def run(self):
        '''Endless Thread to manage incoming data'''
        self.mp_init()

        while not self.stop_event.is_set():
            if len(self.running_threads) < 250:
                # Check for analyze_requests
                for acc in self.account_table.find({"analyze" : True}):
                    task = Thread(target=self.analyze_account, args=(acc["name"],), name=f'Analyze {acc["name"]}', daemon=True)
                    task.start()
                    self.running_threads.append(task)

                # Check for feed_requests
                for acc in self.account_table.find({"make_feed" : True}):
                    task = Thread(target=self.make_feed, args=(acc["name"], False), name=f'Feed Making for {acc["name"]}', daemon=True)
                    task.start()
                    self.running_threads.append(task)

            # Clean running_threads list
            for thread in self.running_threads:
                if not thread.is_alive():
                    self.running_threads.remove(thread)

            time.sleep(0.5)
            continue
            # Try to get an item
            try:
                item = self.data_queue.get(block=True, timeout=0.5)
                task = None

                if "analyze-account" in item["op"]:
                    task = Thread(target=self.analyze_account, args=(item["account"],), name=f'Analyze {item["account"]}', daemon=True)
                if "make-feed" in item["op"]:
                    delete_old = True if ("delete-old" in item and item["delete-old"] is True) else False
                    task = Thread(target=self.make_feed, args=(item["account"], delete_old), name=f'Feed Making for {item["account"]}', daemon=True)

                if task:
                    task.start()
                    self.running_threads.append(task)


            except queues.Empty:
                # Nothing to do --> Clean Thread-List
                for thread in self.running_threads:
                    if not thread.is_alive():
                        self.running_threads.remove(thread)

        # Shut everything down
        for thread in self.running_threads:
            thread.join(timeout=2)


class MP_APIHandler(Process):
    def __init__(self, stop_event, account_manage_queue, stats_manager_queue) -> None:
        super(MP_APIHandler, self).__init__()
        self.stop_event = stop_event
        self.account_manage_queue = account_manage_queue
        self.stats_manager_queue = stats_manager_queue

    def mp_init(self):
        from flask_server import start_server
        self.server_thread = Thread(target=start_server, args=(self, ), name="API Queue Managing", daemon=True)
        self.server_thread.start()

        from agents import AccountSearch, PostSearch, AccessTokenManager
        AccountSearch.init()
        PostSearch.init()
        self.indexer_thread = Thread(target=AccountSearch.create_search_index, name="Account Indexing", daemon=True)
        self.indexer_thread.start()

        AccessTokenManager.init()
        self.token_manager_thread = Thread(target=AccessTokenManager.run, name="Access Token Manager", daemon=True)
        self.token_manager_thread.start()

        from hive import AccountsManager
        AccountsManager.init()
        
    def run(self):
        self.mp_init()       

        while not self.stop_event.is_set():
            time.sleep(1) 
        
        
class MP_StatsManager(Process):
    def __init__(self, stop_event, stats_manager_queue) -> None:
        super(MP_StatsManager, self).__init__()
        self.stop_event = stop_event
        self.stats_manager_queue = stats_manager_queue

    def mp_init(self):
        self.placeholder_report = {"requests" : 0, "connections" : [], "post_queries" : 0, "author_queries" : 0, "post_clicked" : 0, "feed_requested" : 0}
        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
        self.stats_table = self.mongo_client[DATABASE_NAME].stats

        self.requests = []
        self.post_queries = 0
        self.author_queries = 0
        self.post_clicked = 0
        self.feed_getted = 0

    def stats_maker(self):
        '''Endless thread to create stat reports'''
        from hashlib import sha256

        while not self.stop_event.is_set():
            start_time = time.time()
            current_date = datetime.utcnow()
            current_date_stamp = current_date.strftime("%d.%m.%Y")
            current_report = self.stats_table.find_one({"date" : current_date_stamp})

            if not current_report:
                # Create document and next iteration
                self.stats_table.insert_one({
                    "date" : current_date_stamp,
                    "reports" : [{**self.placeholder_report, "hour" : x} for x in range(24)]})
                time.sleep(1)
                continue
            last_hour_report = current_report["reports"][current_date.hour]


            # Statistic Calculations
            hashed_requests = [sha256(addr.encode('utf-8')).hexdigest() for addr in self.requests]
            unique_connections_this_hour = set(hashed_requests + last_hour_report["connections"])

            # Preparing      
            current_hour_report = {
                "hour" : current_date.hour,
                "requests" : last_hour_report["requests"] + len(self.requests),
                "connections" : list(unique_connections_this_hour),
                "post_queries" : last_hour_report["post_queries"] + self.post_queries,
                "author_queries" : last_hour_report["author_queries"] + self.author_queries,
                "post_clicked" : last_hour_report["post_clicked"] + self.post_clicked,
                "feed_requested" : last_hour_report["feed_requested"] + self.feed_getted
            }

            # Reset everything
            self.requests = []
            self.post_queries = 0
            self.author_queries = 0
            self.post_clicked = 0
            self.feed_getted = 0

            # Update hour
            self.stats_table.update_one({"date" : current_date_stamp}, {"$set" : {f"reports.{current_date.hour}" : current_hour_report}})

            # Clear previous data
            for index, report in enumerate(current_report["reports"]):
                if index >= current_date.hour:
                    break

                if isinstance(report["connections"], list):
                    self.stats_table.update_one({"date" : current_date_stamp}, {"$set" : {f"reports.{index}.connections" : len(report["connections"])}})

            while (time.time() - start_time) < (60 * 5) and len(self.requests) == 0:
                # wait until something happens or 5 minutes passes
                # request is always there, when someone does does anything
                # --> checking requests is enough
                time.sleep(0.5)

    def run(self):
        self.mp_init()

        # Start stats maker
        stats_maker_task = Thread(target=self.stats_maker, name="Stats Maker", daemon=True)
        stats_maker_task.start()

        while not self.stop_event.is_set():
            # Try to get an item
            try:
                item = self.stats_manager_queue.get(block=True, timeout=0.5)

                if "add-request" in item["op"] and "r" in item:
                    self.requests.append(item["r"])
                if "add-account-search" in item["op"]:
                    self.author_queries += 1
                if "add-post-search" in item["op"]:
                    self.post_queries += 1
                if "add-feed-request" in item["op"]:
                    self.feed_getted += 1

            except queues.Empty:
                # Nothing to do 
                continue

        # Stop Event
        stats_maker_task.join(timeout=10)


class AccountAnalyzer(Process):
    def __init__(self, account : str) -> None:
        super().__init__()
        self.account = account

    def run(self):
        MongoDB.init_global(post_table = True, account_table = True, banned_table = True)
        
        loop = asyncio.get_event_loop()
        loop.run_until_complete(AccountsManager.analyze_account(self.account))
        loop.close()
        
class AccountFeedMaker(Process):
    def __init__(self, account : str, posts_search_index) -> None:
        super().__init__()
        self.account = account
        PostsCategory.search_index = posts_search_index

    def run(self):
        MongoDB.init_global(post_table = True, account_table = True, banned_table = True)
        
        loop = asyncio.get_event_loop()
        loop.run_until_complete(AccountsManager.make_feed(self.account))
        loop.close()

        



