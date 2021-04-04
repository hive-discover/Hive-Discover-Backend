from config import *

from pymongo import MongoClient
from database import MongoDBAsync, MongoDB

import numpy as np
import nmslib
from hashlib import sha256

from datetime import datetime, timedelta
import asyncio
import time


class PostsCategory():
    @staticmethod
    async def create_search_index(waiting_intervall : int = 1000):
        '''Loads&Creates search index'''   
        # Create Index and load data from DB
        # Only Posts from the last 10 days  
        date = datetime.utcnow() - timedelta(days=10)

        records, data = 0, None
        search_index = nmslib.init(method='hnsw', space='cosinesimil')
        async for post in MongoDBAsync.post_data.find({"timestamp" : {"$gte" : date}}):
            if not post["categories"]:
                continue

            data = np.vstack([post["categories"]])
            search_index.addDataPointBatch(data, ids=[int(post["_id"])])
            records += 1 
            if (records % waiting_intervall) == 0:     
                await asyncio.sleep(0.01)     
        
        # Build and set
        search_index.createIndex({'post': 2}, print_progress=False)
        PostsCategory.search_index = search_index
        PostsCategory.search_records = records

    @staticmethod
    async def search(query_ids : list, k=100) -> dict:
        '''
        Seaches for similar posts to given ids. Returns empty results, when search_index is none
        When succes, every id has k similar posts and count of records
        '''
        results = []
        if PostsCategory.search_index:
            results = []
            async for post in MongoDBAsync.post_data.find({"_id" : {"$in" : query_ids}}):
                # Get post from database
                if post is None or post["categories"] is None or post["categories"] is False:
                    # No post found, not categorzied or not failed categorisation
                    continue
                query = np.array(post["categories"])

                # Start searching        
                ids, distances = PostsCategory.search_index.knnQuery(query, k=k)

                # Setup results
                r = []
                for i, j in sorted(zip(ids, distances), key=lambda x: x[1]):
                    r.append({"score" : float(round(j,3)), "_id" : int(i)})

                results.append({"query_id" : post["_id"], "results" : r})

        return {"results" : results, "records" : PostsCategory.search_records}

    @staticmethod
    def search_with_categories(categories : list, k=100) -> dict:
        '''
        Seaches for posts with given categories. Returns empty results, when search_index is none
        When succes, it returns k posts and count of records
        '''
        results = []
        if PostsCategory.search_index:
            query = np.array(categories)

            # Start searching        
            ids, distances = PostsCategory.search_index.knnQuery(query, k=k)

            # Setup results
            for i, j in sorted(zip(ids, distances), key=lambda x: x[1]):
                results.append({"score" : float(round(j, 3)), "_id" : int(i)})

        return {"results" : results, "records" : PostsCategory.search_records}

    @staticmethod
    @DeprecationWarning
    def categorize_post(tok_text : list) -> list:
        '''
        Categorize a post and return that
        None --> Failed (to less words or something else)
        List --> Succes
        '''
        import torch as T

        vectors = []
        for word in tok_text:
            # Calc word vectors
            try:
                vectors.append(statics.FASTTEXT_MODEL.wv[word])
            except:
                pass
        
        if len(vectors) < MIN_KNOWN_WORDS:
            return None

        # DO AI
        _input = T.Tensor([vectors]) # [Batch-Dim, Word, Vectors]
        _output = statics.TEXTCNN_MODEL(_input) # [Batch-Dim, Categories] 

        return _output.data[0].tolist()


class AccountSearch():
    @staticmethod
    def init():
        AccountSearch.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT, username=DATABASE_USER, password=DATABASE_PASSWORD)
        AccountSearch.account_info = AccountSearch.mongo_client[DATABASE_NAME].account_info
        AccountSearch.search_index = None
        AccountSearch.search_records = 0

    @staticmethod
    def get_character_frequenzy(word : str) -> list:
        '''Creates an array with the frequenzy of a character'''
        representation = [0 for _ in FREQUENZY_CHARACTERS]

        # iterate though word
        for c in word:    
            for index, _ in enumerate(representation):
                # find current character index
                if FREQUENZY_CHARACTERS[index] == c:
                    # Found: add 1 and break this loop to get to the next char
                    representation[index] += 1              
                    break

        return np.array(representation)

    @staticmethod
    def create_search_index() -> None:
        '''Generates a search_index (nmslib) of all accounts'''   
        import nmslib
        last_indexing_count = 0    
        while 1: 
            records = 0 # equals also to index
            search_index = nmslib.init(method='hnsw', space='cosinesimil')
            
            # wait until new accounts were added or the search_index is never created
            while AccountSearch.search_index and last_indexing_count == AccountSearch.accounts_table.count_documents({}):
                time.sleep(60)
            last_indexing_count = AccountSearch.accounts_table.count_documents({})

            # Process all accounts
            for account in AccountSearch.accounts_table.find():
                # Get character frequenzy and add it to search_index
                representation = AccountSearch.get_character_frequenzy(account["name"])
                data = np.vstack([representation])
                search_index.addDataPointBatch(data, ids=[records]) # index = id = record

                # Set index
                if not "index" in account or account["index"] != records:
                    AccountSearch.accounts_table.update_one({"name" : account["name"]}, {"$set" : {"index" : records}})
                records += 1           

            # Build, set and wait
            search_index.createIndex({'post': 2}, print_progress=False)
            AccountSearch.search_index = search_index
            AccountSearch.search_records = records
            time.sleep(60 * 30)

    @staticmethod
    def search_by_username(query_str : str, max=50) -> dict:
        '''Searches for an Account based on Username'''
        start_time = time.time()
        results = []

        if AccountSearch.search_index:           
            # Process query, search, sort and extract indexes    
            query = AccountSearch.get_character_frequenzy(query_str)
            ids, distances = AccountSearch.search_index.knnQuery(query, k=max)     
            
            for _id, _distance in zip(ids, distances):
                acc = AccountSearch.accounts_table.find_one({"index" : int(_id)})
                if acc and acc["name"]:# not in results:
                    if query_str in acc["name"]:
                        _distance -= 1
                    results.append((acc["name"], _distance))
        
        return {"results" : [zipped[0] for zipped in sorted(results, key=lambda x:x[1])] , "seconds" : (time.time() - start_time), "records" : AccountSearch.search_records}

    @staticmethod
    def search_by_bio(query_str : str, max=50) -> dict:
        '''Searches for Accounts based on Profile Information'''
        start_time = time.time()
        
        # Search
        findings = AccountSearch.account_info.find({"$text" : {"$search" : query_str}}, { "score": { "$meta": "textScore" }})
        findings.sort([('score', { "$meta": "textScore" })]).limit(max)


        return {"results" : [acc["name"] for acc in findings], "seconds" : (time.time() - start_time), "records" : AccountSearch.search_records}

class AccessTokenManager():
    @staticmethod
    def init() -> None:
        AccessTokenManager.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT, username=DATABASE_USER, password=DATABASE_PASSWORD)
        AccessTokenManager.accounts_info = AccessTokenManager.mongo_client[DATABASE_NAME].account_info

        # Open_tokens are tokens which has to check or update
        AccessTokenManager.open_tokens = [] # (username, token)

    @staticmethod
    def run():
        '''Running agent to manage access_tokens'''
        from hivesigner.client import Client
        username, token, acc = None, None, None
        while 1:
            if len(AccessTokenManager.open_tokens) == 0:
                time.sleep(0.05)
                continue

            # Get item and check if acc exists
            username, token = AccessTokenManager.open_tokens.pop(0)

            acc = AccessTokenManager.accounts_info.find_one({"name" : username})
            if not acc or token is None:
                # Something wrong goes (like someone entered BULLSHIT or got deleted)
                continue

            # Check if valid
            try:
                c = Client(access_token=token)
                data = c.me()
                valid = ("user" in data and data["user"] == username)
            except:
                # SSL Error or something, just continue it will be made again when the user logges later in
                continue
            
            if valid:
                AccessTokenManager.accounts_info.update({"name" : username}, {"$set" : {"access_token" : sha256(token.encode('utf-8')).hexdigest()}})
            else:
                # Reset key in DB, but let key prove again and then maybe it is reentered
                if "access_token" in acc:
                    AccessTokenManager.open_tokens.append((username, acc["access_token"]))
                AccessTokenManager.accounts_info.update({"name" : username}, {"$unset" : {"access_token" : ""}})

    @staticmethod
    async def check_access_token(username : str, token : str) -> bool:
        '''Checks a given access_token by entering it in hive_signer'''
        AccessTokenManager.open_tokens.append((username, token))

        # test first, if access_token is inside db
        acc = await MongoDB.accounts_info.find_one({"name" : username})
        if acc and "access_token" in acc and acc["access_token"] == sha256(token.encode('utf-8')).hexdigest():
            # Inside db and correct
            return True

        # Token not in DB (maybe key in DB is to old, revoked or first time)
        # --> check
        from hivesigner.client import Client
        c = await Client(access_token=token)
        data = c.me()
        return ("user" in data and data["user"] == username)
            
    

class Statistics():
    def __init__(self):
        self.placeholder_report = {"requests" : 0, "connections" : [], "post_queries" : 0, "author_queries" : 0, "post_clicked" : 0, "feed_requested" : 0}
        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT, username=DATABASE_NAME, password=DATABASE_PASSWORD)
        self.stats_table = self.mongo_client[DATABASE_NAME].stats

        self.requests = []
        self.post_queries = 0
        self.author_queries = 0
        self.post_clicked = 0
        self.feed_getted = 0

    def run(self):
        '''Manage reports'''
        while 1:
            start_time = time.time()
            current_date = datetime.utcnow()
            current_date_stamp = current_date.strftime("%d.%m.%Y")
            current_report = self.stats_table.find_one({"date" : current_date_stamp})

            if not current_report:
                # Create document and next iteration
                self.stats_table.insert_one({
                    "date" : current_date_stamp,
                    "reports" : [{**self.placeholder_report, "hour" : x} for x in range(24)]})
                time.sleep(0.5)
                continue
            last_hour_report = current_report["reports"][current_date.hour]


            # Statistic Calculations
            unique_connections_this_hour = set(self.requests + last_hour_report["connections"])

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

    def add_request(self, request):
        self.requests.append(request.remote_addr)

    def add_post_query(self):
        self.post_queries += 1

    def add_author_query(self):
        self.author_queries += 1

    def add_post_clicked(self):
        self.post_clicked += 1

    def add_get_feed(self):
        self.feed_getted += 1

    @staticmethod
    def get_statistics(date = None) -> dict:
        '''Prepares a statistic dict with all data and return it'''
        mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT, username=DATABASE_USER, password=DATABASE_PASSWORD)
        stats_table = mongo_client[DATABASE_NAME].stats

        if not date:
            date = datetime.utcnow()

        if isinstance(date, datetime):
            date = date.strftime("%d.%m.%Y")
        if not isinstance(date, str):
            return {"status" : "failed", "info" : "date is invalid", "date" : date}


        report = stats_table.find_one({"date" : date})
        if not report:
            return {"status" : "failed", "info" : "report for this date does not exist", "date" : date}
        
        hours_data = []
        for hour_report in report["reports"]:
            if isinstance(hour_report["connections"], list):
                hour_report["connections"] = len(hour_report["connections"])
            hours_data.append(hour_report)

        return {"status" : "ok", "data" : hours_data, "date" : date}

