from datetime import datetime
from config import *
import helper
import network

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
from nltk.stem.wordnet import WordNetLemmatizer

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
                if post["weighted_doc_vectors"] is None or post["weighted_doc_vectors"] is False:
                    # False means that to low words are available
                    continue

                data = np.vstack([post["weighted_doc_vectors"]])
                search_index.addDataPointBatch(data, ids=[int(post["post_id"])])
                records += 1           
            
            # Build and set
            search_index.createIndex({'post': 2}, print_progress=False)
            self.search_index = search_index
            self.search_records = records
            del records, search_index

            # weight all posts
            start_time = time.time()
            while((time.time() - start_time) <= MAX_SEARCH_INDEX_DELTA):
                # get all unweighted english posts
                tok_text, authors, permlinks = [], [], []
                for post in self.post_table.find({"weighted_doc_vectors" : None, "lang" : "__label__en"}):
                    # Load and Prepare
                    try:
                        post = Comment(f"@{post['author']}/{post['permlink']}")
                    except ContentDoesNotExistsException:
                        # Delete
                        self.post_table.delete_one({"author" : post['author'], "permlink" : post['permlink']})
                        continue

                    text = post["title"] + ". "
                    text += ' '.join(helper.html_to_text(post["body"]))               
                    text = helper.pre_process_text(text)

                    authors.append(post['author'])
                    permlinks.append(post['permlink'])
                    tok_text.append(helper.tokenize_text(text))

                    if len(tok_text) > 30:
                        # Prevent overflow
                        break

                if len(tok_text) == 0:
                    # Nothing to do -> create search index
                    break
                
                # Enter all weightings
                weighted_docs = PostSearcher.weighten_doc(tok_text)
                for index, weight_doc in enumerate(weighted_docs):
                    value = False
                    if not weight_doc is None and len(weight_doc) > MIN_KNOWN_WORDS:
                        # If enough words
                        value = weight_doc

                    # Update
                    self.post_table.update_one({"author" : authors[index], "permlink" : permlinks[index]},
                                                    { "$set" : {"weighted_doc_vectors" : value} })

                del tok_text, weighted_docs, permlinks, authors
  
    def search(self, query_string : str, k=100) -> dict:
        '''Searches the Index for a specified query and returns ids. Returns empty results and -1 seconds, when search_index is none'''
        results, seconds = [], -1
        if self.search_index:
            query_string = statics.LEMMATIZER.lemmatize(query_string.lower())
            query = [statics.WORD2VEC_MODEL[vec] for vec in query_string.split()]
            query = np.mean(query,axis=0)

            # Start searching and measure time
            t_start = time.time()            
            ids, distances = self.search_index.knnQuery(query, k=k)
            seconds = float(time.time() - t_start)

            # Setup results
            for i, j in sorted(zip(ids, distances), key=lambda x: x[1]):
                results.append({"score" : float(round(j,2)), "post_id" : int(i)})

        return {"results" : results, "seconds" : seconds, "records" : self.search_records}


    @staticmethod
    def weighten_doc(tok_text : list) -> list:
        '''
        Weighten A Doc for Search Engine (tok_text is in english)
        None --> Failed (to less words or something else)
        List --> Succes
        '''
        if len(tok_text) == 0:
            return None
        
        all_vocabs_as_sentence = network.get_all_vocabs_as_sentence()
        bm25 = BM25Okapi(tok_text + all_vocabs_as_sentence) # with all vocabs

        doc_vectors_all = []
        for index, text in enumerate(tok_text):
            doc_vector = []
            for word in text:
                #if word in statics.WORD2VEC_MODEL.wv.vocab:
                # Vectorize
                try:
                    vector = statics.FASTTEXT_MODEL.wv[word]
                    weight = (bm25.idf[word] * ((bm25.k1 + 1.0)*bm25.doc_freqs[index][word])) / (bm25.k1 * (1.0 - bm25.b + bm25.b *(bm25.doc_len[index]/bm25.avgdl))+bm25.doc_freqs[index][word])
                    # Weighten
                    weighted_vector = vector * weight
                    doc_vector.append(weighted_vector)
                except:
                    pass

            if len(doc_vector) == 0:
                doc_vectors_all.append(None)
            else:
                doc_vector_mean = np.mean(doc_vector,axis=0)
                doc_vectors_all.append(doc_vector_mean.tolist())
            
        return doc_vectors_all



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
                if post["categories_doc"] is None or post["categories_doc"] is False:
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
                if post is None or post["categories_doc"] is None or post["categories_doc"] is False:
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
            #if word in statics.WORD2VEC_MODEL.wv.vocab:
                #vectors.append(statics.WORD2VEC_MODEL[word])
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
    def __init__(self) -> None:
        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
        self.accounts_table = self.mongo_client[DATABASE_NAME].accounts

        self.bm25 = None
        self.search_records = 0

    def create_search_index(self):
        '''Generates a bm25 object of all accounts'''
        while 1:          
            records = 0 # equals also to index
            accs = []
            for account in self.accounts_table.find():
                # Get all accounts
                # Add them as splitted string: h e l l o
                accs.append(' '.join([c for c in account["name"]]))

                # Set index
                self.accounts_table.update_one({"name" : account["name"]}, {"$set" : {"index" : records}})
                records += 1           
            
            if len(accs) == 0:
                # wait
                time.sleep(20)
                continue

            # Build and set
            self.bm25 = BM25Okapi(accs)
            self.search_records = records

            del records, accs
            # wait
            time.sleep(120)

    def search(self, query : str, max=20) -> list:
        '''Searches for an Account'''
        if self.bm25 is None:
            return []

        # Split query and search
        start_time = time.time()
        tokenized_query = ' '.join([c for c in query])
        acc_scores = self.bm25.get_scores(tokenized_query)
        seconds = time.time() - start_time

        # Combine to index and sort
        results = []
        for index, score in sorted(zip(range(0, self.search_records), acc_scores), key=lambda x: x[1], reverse=True):
            acc = self.accounts_table.find_one({"index" : index})
            if acc:
                # Insert
                results.append(acc["name"])

            if len(results) > max:
                break

        return {"results" : results, "seconds" : seconds, "records" : self.search_records}

            

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

                # Check if categories is set:
                if post_data["categories_doc"] is None or post_data["categories_doc"] is False:
                    # Not categorized
                    continue

                # Process
                is_post = False
                if index < len(posts):
                    # His Post
                    self.profiler["posts"] = list(self.profiler["posts"]) + [post_data["post_id"]]
                    is_post = True
                else:
                    # His Vote
                    self.profiler["votes"] = list(self.profiler["votes"]) + [post_data["post_id"]]

                categories = np.array(post_data["categories_doc"])

                if is_post:
                    # Double all values (posts count more)
                    categories *= 2 

                if self.profiler["categories"] is None:
                    # First Element
                    self.profiler["categories"] = categories
                else:
                    # Calc Average
                    self.profiler["categories"] += categories
                

            except ContentDoesNotExistsException:
                continue

        # Finished
        self.profiler["last_analyze"] = datetime.utcnow()
        self.profiler["loading"] = False
        self.update_profiler()
        
    def check_if_post_seen(self, post_id : int) -> bool:
        '''Checks if a post wroted by him or voted'''
        if post_id in self.profiler["posts"]:
            return True
        if post_id in self.profiler["votes"]:
            return True
        if post_id in self.profiler["feed"]:
            return True
        
        return False
    
    def make_feed(self) -> None:
        '''Tries to get interesting stuff for an account based on categories and his own posts'''
        # 1. Wait until at least one post/vote is available
        while len(self.profiler["posts"]) == 0 or self.profiler["categories"] is None:
            time.sleep(0.5)

        # 2. Fill Feed-List
        self.profiler["feed"] = []
        np.random.seed(int((time.time() / 100)))
        while(PROFILER_MAX_FEED_LEN > len(self.profiler["feed"])):

            # 3. Choose Feed Type (at least one post)
            rnd = np.random.randint(0, 2)
            ids = []
            if rnd == 0 and len(self.profiler["posts"]) > 0:
                # Similar Post type
                # Choose a random post as base and search for similar
                base_post_ids = [random.choice(self.profiler["posts"]),  random.choice(self.profiler["posts"]), random.choice(self.profiler["posts"])] 
                for result in statics.POSTS_CATEGORY.search(base_post_ids, k=20)["results"]:
                    ids += [random.choice([x["post_id"] for x in result["results"]])]
            elif not self.profiler["categories"] is None:
                # Based on category type
                # Calc categories to percentages
                total = np.sum(self.profiler["categories"])
                percentage_cats = [(x/total) for x in self.profiler["categories"]]

                # Find good results
                ids += [random.choice(statics.POSTS_CATEGORY.search_with_categories(percentage_cats, k=70)["results"])["post_id"]]

            # 4. Add to Profiler Feed       
            for id in ids:
                # Check if already seen
                if self.check_if_post_seen(id) is False:
                    self.profiler["feed"] = list(self.profiler["feed"]) + [id]    
            
            self.update_profiler()

    def get_feed(self) -> dict:
        '''Returns a finished feed with permlinks, authors and so on'''
        if len(self.profiler["feed"]) == 0:
            return {}

        # Get randoms
        feed_list = [] 
        while len(feed_list) < 20 and len(feed_list) != len(self.profiler["feed"]): 
            x = random.choice(self.profiler["feed"])
            if not x in feed_list:
                feed_list.append(x)

        # Process it
        return_feed = {"status" : "ok", "posts" : []}
        for post_id in feed_list:
            post = self.mongo_client[DATABASE_NAME].posts.find_one({"post_id" : post_id})
            if post:
                # Insert author and permlink
                return_feed["posts"] = list(return_feed["posts"]) + [{"author" : post["author"], "permlink" : post["permlink"]}]
            
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


class Lemmatizer():
    def __init__(self):
        self.lmmze = WordNetLemmatizer()
        self.working = False

    def lemmatize(self, text : str) -> str:
        while self.working:
            time.sleep(0.1)

        self.working = True
        text = self.lmmze.lemmatize(text)
        self.working = False
        return text




