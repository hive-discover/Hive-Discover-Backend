from datetime import datetime
from config import *
import helper

import pymongo
from pymongo import MongoClient

from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.nodelist import NodeList
from beem.exceptions import ContentDoesNotExistsException
from beem.vote import AccountVotes

import torch as T
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from rank_bm25 import BM25Okapi
import nmslib
import spacy
from ftfy import *

import time
import random
from threading import Thread

instance = Hive(node=NodeList().get_nodes(hive=True))


class PostSearcher():
    def __init__(self) -> None:
        # Database
        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
        self.post_table = self.mongo_client[DATABASE_NAME].posts

        self.search_index = None
        self.search_records = 0

    def create_search_index(self):
        '''Endless Thread: Loads&Creates search index'''
        while 1:
            # Create Index and load data from Database
            records = 0
            search_index = nmslib.init(method='hnsw', space='cosinesimil')
            for post in self.post_table.find():
                if post["weighted_doc_vectors"] is None:
                    continue

                data = np.vstack([post["weighted_doc_vectors"]])
                search_index.addDataPointBatch(data, ids=[int(post["post_id"])])
                records += 1           
            
            # Build and set
            search_index.createIndex({'post': 2}, print_progress=False)
            self.search_index = search_index
            self.search_records = records

            del records, search_index
            # wait
            time.sleep(120)
   
    def search(self, query_string : str, k=100) -> dict:
        '''Searches the Index for a specified query and returns ids. Returns empty results and -1 seconds, when search_index is none'''

        results, seconds = [], -1
        if self.search_index:
            query = [statics.WORD2VEC_MODEL[vec] for vec in query_string.lower().split()]
            query = np.mean(query,axis=0)

            # Start searching and measure time
            t_start = time.time()            
            ids, distances = self.search_index.knnQuery(query, k=k)
            seconds = float(time.time() - t_start)

            # Setup results
            for i, j in sorted(zip(ids, distances), key=lambda x: x[1], reverse=True):
                results.append({"score" : float(round(j,2)), "post_id" : int(i)})

        return {"results" : results, "seconds" : seconds, "records" : self.search_records}


    @staticmethod
    def weighten_doc(tok_text : list) -> list:
        '''
        Weighten A Doc for Search Engine
        None --> Failed (to less words or something else)
        List --> Succes
        '''
        if len(tok_text) == 0:
            return None
            
        tok_text = [tok_text]
        bm25 = BM25Okapi(tok_text)

        doc_vector = []
        for word in tok_text[0]:
            if word in statics.WORD2VEC_MODEL.wv.vocab:
                # Vectorize
                vector = statics.WORD2VEC_MODEL.wv.word_vec(word)
                weight = (bm25.idf[word] * ((bm25.k1 + 1.0)*bm25.doc_freqs[0][word])) / (bm25.k1 * (1.0 - bm25.b + bm25.b *(bm25.doc_len[0]/bm25.avgdl))+bm25.doc_freqs[0][word])
                # Weighten
                weighted_vector = vector * weight
                doc_vector.append(weighted_vector)

        if len(doc_vector) > MIN_KNOWN_WORDS:
            # Only return when enough words are available
            doc_vector_mean = np.mean(doc_vector,axis=0)
            return doc_vector_mean.tolist()
            
        return None



class PostsCategory():
    def __init__(self) -> None:
        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
        self.post_table = self.mongo_client[DATABASE_NAME].posts

        self.search_index = None
        self.search_records = 0

    def create_search_index(self):
        '''Endless Thread: Loads&Creates search index'''
        while 1:
            # Create Index and load data from Database
            records = 0
            search_index = nmslib.init(method='hnsw', space='cosinesimil')
            for post in self.post_table.find():
                if post["categories_doc"] is None:
                    continue

                data = np.vstack([post["categories_doc"]])
                search_index.addDataPointBatch(data, ids=[int(post["post_id"])])
                records += 1           
            
            # Build and set
            search_index.createIndex({'post': 2}, print_progress=False)
            self.search_index = search_index
            self.search_records = records

            del records, search_index
            # wait
            time.sleep(120)

    def search(self, query_ids : list, k=100) -> dict:
        '''
        Seaches for similar posts to given ids. Returns empty results, when search_index is none
        When succes, every id has k similar posts and count of records
        '''
        results = []
        if self.search_index:
            for current_post_id in query_ids:
                # Get post from database
                post = self.post_table.find_one({"post_id" : current_post_id})
                if post is None:
                    # No post found with given id
                    continue
                query = np.array(post["categories_doc"])

                # Start searching        
                ids, distances = self.search_index.knnQuery(query, k=k)

                # Setup results
                r = []
                for i, j in sorted(zip(ids, distances), key=lambda x: x[1]):
                    r.append({"score" : float(round(j,3)), "post_id" : int(i)})

                results.append({"query_id" : current_post_id, "results" : r})

        return {"results" : results, "records" : self.search_records}

    def search_with_categories(self, categories : list, k=100) -> dict:
        '''
        Seaches for posts with given categories. Returns empty results, when search_index is none
        When succes, it returns k posts and count of records
        '''
        results = []
        if self.search_index:
            query = np.array(categories)

            # Start searching        
            ids, distances = self.search_index.knnQuery(query, k=k)

            # Setup results
            for i, j in sorted(zip(ids, distances), key=lambda x: x[1]):
                results.append({"score" : float(round(j, 3)), "post_id" : int(i)})

        return {"results" : results, "records" : self.search_records}

    @staticmethod
    def categorize_post(tok_text : list) -> list:
        '''
        Categorize a post and return that
        None --> Failed (to less words or something else)
        List --> Succes
        '''
        vectors = []
        for word in tok_text:
            # Calc word vectors
            if word in statics.WORD2VEC_MODEL.wv.vocab:
                vectors.append(statics.WORD2VEC_MODEL.wv.word_vec(word))
        
        if len(vectors) < MIN_KNOWN_WORDS:
            return None

        # DO AI
        _input = T.Tensor([vectors]) # [Batch-Dim, Word, Vectors]
        _output = statics.TEXTCNN_MODEL(_input) # [Batch-Dim, Categories] 

        return _output.data[0].tolist()



class Profiler():
    def __init__(self, username : str, start_analyse_when_create=True) -> None:
        self.username = username
        self.account = Account(username, blockchain_instance=instance)

        # Database connection
        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
        self.profiler_table = self.mongo_client[DATABASE_NAME].profiler

        self.profiler = self.profiler_table.find_one({"username" : username})
        created = False
        if self.profiler is None:
            # Create profiler
            self.profiler = Profiler.create_profiler(username, self.mongo_client)
            created = True

        if start_analyse_when_create and (created or self.profiler["last_analyze"] is None):
            t = Thread(target=self.analyze_activities, daemon=True, name="Analyse Activities from " + username)
            t.start()

    def update_profiler(self) -> None:
        '''Updates the Database Entry for this profiler'''
        save_state = self.profiler

        if not save_state["categories"] is None:
            # Convert to list
            save_state["categories"] = list(save_state["categories"])

        # Save
        self.profiler_table.update_one({"username" : self.username}, { "$set" : self.profiler })

    def analyze_activities(self) -> None:
        '''Run as Thread: Get activities  '''   
        self.profiler["loading"] = True
        self.profiler["posts"] = []
        self.profiler["categories"] = None


        votes, posts = [], []
        for operation in self.account.history_reverse(only_ops=['comment', 'vote']):
            # Get activities
            if operation["type"] == "vote" and len(votes) < PROFILER_MAX_VOTES:
                if operation["voter"] == self.username and operation["voter"] != operation["author"]:
                    # Vote from him to a foreign post
                    votes.append((operation['author'], operation['permlink']))

            if operation["type"] == "comment":
                if operation["author"] == self.username:
                    # He wrote the Post and is no comment
                    if operation["parent_author"] == '':
                        posts.append((operation['author'], operation['permlink']))


        # Make Categories and list Posts
        self.profiler["loading"] = {"current" : 0, "max" : len(posts + votes)}
        for index, (author, permlink) in enumerate(posts + votes):
            try:
                # Show loading
                self.profiler["loading"]["current"] = index
                self.update_profiler()

                # Check if already inside database
                post_data = self.mongo_client[DATABASE_NAME].posts.find_one({"author" : author, "permlink" : permlink})
                if post_data is None:
                    # Not inside --> Get and Append
                    post = Comment(f"@{author}/{permlink}")
                    time.sleep(0.5)
                    if post.parent_permlink != '':
                        # Is comment
                        continue

                    # No Comment
                    post_id = statics.POSTS_MANAGER.append_post(post, timestamp=post["created"])
                    if post_id < 0:
                        continue

                    post_data = self.mongo_client[DATABASE_NAME].posts.find_one({"post_id" : post_id})

                # Process
                if index < len(posts):
                    # His Post
                    self.profiler["posts"] = list(self.profiler["posts"]) + [post_data["post_id"]]
                    continue

                # His Vote
                self.profiler["votes"] = list(self.profiler["votes"]) + [post_data["post_id"]]
                categories = np.array(post_data["categories_doc"])

                if self.profiler["categories"] is None:
                    # First Element
                    self.profiler["categories"] = categories
                else:
                    # Calc Average
                    self.profiler["categories"] += categories #np.array(np.add(self.profiler["categories"], categories) / 2)
                

            except ContentDoesNotExistsException:
                continue

        # Finished
        self.profiler["last_analyze"] = datetime.utcnow()
        self.profiler["loading"] = False
        self.update_profiler()
        
    def make_feed(self) -> None:
        '''Tries to get interesting stuff for an account based on categories and his own posts'''
        # 1. Wait until at least one post/vote is available
        while len(self.profiler["posts"]) == 0 or self.profiler["categories"] is None:
            time.sleep(0.5)

        # 2. Fill Feed-List
        np.random.seed(int((time.time() / 100)))
        for index in range(PROFILER_MAX_FEED_LEN - len(self.profiler["feed"])):
            feed_obj = {"type" : None, "post_ids" : []}
            search_results = []
            
            # 3. Choose Feed Type (at least one post)
            rnd = np.random.randint(0, 2)
            if rnd == 0 and len(self.profiler["posts"]) > 0:
                # Similar Post type
                feed_obj["type"] = "similar_post"
                
                # Choose a random post as base and search for similar
                base_post_id = random.choice(self.profiler["posts"])  
                feed_obj["base_id"] = base_post_id
                search_results = statics.POSTS_CATEGORY.search([base_post_id])["results"][0]["results"]

            else:
                # Based on category type
                feed_obj["type"] = "category_based"

                # Calc categories to percentages
                total = np.sum(self.profiler["categories"])
                percentage_cats = [(x/total) for x in self.profiler["categories"]]

                # Find good results
                search_results = statics.POSTS_CATEGORY.search_with_categories(percentage_cats)["results"]


            # 4. Process Search Results
            if len(search_results) == 0:
                # Something gone wrong
                continue
            
            # Add them
            for result in search_results:                
                if result["post_id"] in self.profiler["posts"]:
                    continue

                # TODO: Implement Vote Check

                feed_obj["post_ids"] = list(feed_obj["post_ids"]) + [result["post_id"]]
                if len(feed_obj["post_ids"]) >= PROFILER_MAX_FEED_POSTS_LEN:
                    # Limit reached
                    break
              

            # 5. Add to Profiler Feed
            self.profiler["feed"] = list(self.profiler["feed"]) + [feed_obj]
            self.update_profiler()

    def get_feed(self) -> dict:
        '''Returns a finished feed with permlinks, authors and so on'''
        if len(self.profiler["feed"]) == 0:
            return {}

        # Get random and delete old
        feed_list = self.profiler["feed"]
        feed = random.choice(feed_list)

        feed_list.remove(feed)
        self.profiler["feed"] = feed_list
        self.update_profiler()

        # Process it
        return_feed = {"type" : feed["type"], "posts" : []}
        for post_id in feed["post_ids"]:
            post = self.mongo_client[DATABASE_NAME].posts.find_one({"post_id" : post_id})
            if post:
                # Insert author and permlink
                return_feed["posts"] = list(return_feed["posts"]) + [{"author" : post["author"], "permlink" : post["permlink"]}]
            
        if feed["type"] == "similar_post":
            post = self.mongo_client[DATABASE_NAME].posts.find_one({"post_id" : feed["base_id"]})
            if post:
                return_feed["base_post"] = {"author" : post["author"], "permlink" : post["permlink"]}

        return return_feed     

                    
    @staticmethod
    def create_profiler(username : str, mongo_client : MongoClient) -> dict:
        '''
        Create a profiler object and insert it into database. It will later load
        '''
        profiler = {"username" : username, "posts" : [], "votes" : [], "categories" : None, "last_analyze" : None, "loading" : True, "feed" : []}

        # Insert
        collection = mongo_client[DATABASE_NAME].profiler
        collection.insert_one(profiler)

        return profiler







