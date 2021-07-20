import asyncio, time
import json
import math
import requests
from datetime import timezone, timedelta
import sys, os
sys.path.append(os.getcwd() + "/.")

import base64
import torch as T
import numpy as np

import aiohttp
from pymongo.errors import BulkWriteError
from pymongo import UpdateMany, UpdateOne

import nltk
from nltk.corpus import stopwords

from network import TextCNN
from config import *
from helper import helper, Lemmatizer
from database import MongoDBAsync

class statics:
    TEXT_CNN : TextCNN = None
    LMZT : Lemmatizer = None
    Bulk_PostData_Updates : list = []
    Bulk_PostText_Updates : list = []
    AmableDB_Inserts = []

AMABLE_DB_URL = f"http://api.hive-discover.tech:{AMABLE_DB_Port}"

# amableDB Operations
async def perform_amabledb_inserts():
    '''Insert Docs into AmableDB'''
    if len(statics.AmableDB_Inserts) == 0:
        return

    # Prepare Request
    posts_count = len(statics.AmableDB_Inserts)
    payload = {"post_cats" : statics.AmableDB_Inserts}
    statics.AmableDB_Inserts = []

    # Make Create-Request
    async with aiohttp.ClientSession(headers={'Content-Type': 'application/json'}) as session:
        async with session.post(AMABLE_DB_URL + "/create", json=payload) as response:
            if not response or response.status != 200:
                print("[Failed] Cannot insert {posts_count} documents into amabledb!")
                print(response.status)
                print(await response.text())
                await asyncio.sleep(5)
                exit()
            else:
                print(f"[Success] entered {posts_count} posts in amableDB")

    # Rebuild KNN Index
    payload = { "catsKNN": { "collection": "post_cats", "build": True } }
    async with aiohttp.ClientSession(headers={'Content-Type': 'application/json'}) as session:    
        async with session.post(AMABLE_DB_URL + "/index", json=payload) as response:
            if not response or response.status != 200:  
                print(f"[Failed] Cannot rebuild catsKNN Index!")
                print(response.status)
                print(await response.text())
                await asyncio.sleep(5)
                exit()

            response = json.loads(await response.text())
            if "status" not in response or response["status"] != "ok":
                print(f"[Failed] Cannot rebuild catsKNN Index!")
                print(response)
                await asyncio.sleep(5) # Not exit, let it run

def load_models() -> None:
    '''Load TextCnn and lmtz'''
    statics.TEXT_CNN, loaded = TextCNN.load_model()
    statics.LMZT = Lemmatizer()
    print(f"Loaded TextCNN from Disk? - {loaded}")

def remove_stopwords(tok_body : list) -> str:
    if not tok_body or len(tok_body) == 0:
        return ""

    return " ".join([word for word in tok_body if word not in stopwords.words("english")])

async def get_word_vectors(tok_body : list) -> list:
    server_vectors = []
    # Get them from the server
    async with aiohttp.ClientSession(headers={'Content-Type': 'application/json'}) as session:
        # Async Session
        url = f"https://api.hive-discover.tech:{WORDVEC_API_PORT}/vector"
        async with session.post(url, json=tok_body) as response:        
            if not response or response.status != 200:
                # Network Error
                print("Network Error while getting Vectors from API!")
                print(response)
                print(response.status)
                print(await response.text())
                time.sleep(15)
                exit(-2)

            data = json.loads(await response.text())
            if "status" not in data or data["status"] != "ok":
                # Server Error
                print("Server Error while getting Vectors from API!")
                print(response)
                print(await response.text())
                time.sleep(15)
                exit(-3)

            # Got everything
            server_vectors = data["vectors"]

    # Decode vectors and map them as an ordered list
    vectors = []    
    for word in tok_body:
        # Check if the word is available as a vector
        if word in server_vectors:
            d_bytes = base64.b64decode(server_vectors[word])
            vectors.append(np.frombuffer(d_bytes, dtype=np.float64))


    return vectors


async def process_one_post(post : dict) -> None:
    # Prepare, Tokenize and Vectorize Text
    text = ""
    if "title" in post:
        text += post["title"] + ". "
    if "body" in post:
        text += post["body"] + ". "
    if "tags" in post:
        text += post["tags"]
    text = helper.pre_process_text(text, lmtz=statics.LMZT)
    tok_text = helper.tokenize_text(text)
    vectors = await get_word_vectors(tok_text)

    # Calculate Category-Values
    if len(vectors) < MIN_KNOWN_WORDS:
        # Not enough words
        categories = False
    else:
        # DO AI
        _input = T.Tensor([vectors]) # _input.shape = [Batch-Dim, Word, Vectors]
        _output = statics.TEXT_CNN(_input) # _output.shape = [Batch-Dim, Categories] 
        categories = _output.data[0].tolist()

    # post_data Update
    statics.Bulk_PostData_Updates.append(
        UpdateOne({"_id" : post["_id"]}, {"$set" : {"categories" : categories}})
    )

    # post_text Update
    statics.Bulk_PostText_Updates.append(
        UpdateOne({"_id" : post["_id"]}, {"$set" : {"body" : remove_stopwords(tok_text)}})
    )

    # amableDB Insert with TTL settings
    sevendays_later = post["timestamp"] + timedelta(days=10)
    sevendays_later = sevendays_later.replace(tzinfo=timezone.utc)
    sevendays_later = math.ceil(sevendays_later.timestamp()) # seconds from 1970
    statics.AmableDB_Inserts.append({"id" : post["_id"], "categories" : categories, "&ttl" : sevendays_later})

async def run(BATCH_SIZE : int = 25) -> None:
    # Init
    nltk.download("stopwords")
    load_models()
    MongoDBAsync.init_global(post_table=True)
    helper.init()

    AGGREGATION_PIPELINE = [
        {"$match" : {"categories" : None, "lang.lang" : "en"}},
        {"$sample" : {"size" : BATCH_SIZE}}
    ]

    while 1:
        tasks = []

        # Get (randomly) open posts
        open_posts_ids = []
        async for current_post in MongoDBAsync.post_data.aggregate(AGGREGATION_PIPELINE):   
            if len(open_posts_ids) >= BATCH_SIZE:
                break
            open_posts_ids.append(current_post["_id"])

        # No open_posts? ==> wait half a minute and continue
        if len(open_posts_ids) == 0:
            await asyncio.sleep(30)
            continue


        # Got something to do ==> Get text-data and start processing
        async for current_post in MongoDBAsync.post_text.find({"_id" : {"$in" : open_posts_ids}}):
            tasks.append(process_one_post(current_post))
               
        # Wait for everything to has finished
        if len(tasks) > 0:
            await asyncio.wait(tasks)

        # Update Bulks for post_data       
        async def doPostDataUpdate():
            if len(statics.Bulk_PostData_Updates) == 0:
                return

            try:
                await MongoDBAsync.post_data.bulk_write(statics.Bulk_PostData_Updates, ordered=False)
            except BulkWriteError as ex:
                print("Error on BulkWrite for post_data:")
                print(ex)
            statics.Bulk_PostData_Updates = []                    

        # Update Bulks for post_text        
        async def doPostTextUpdate():
            if len(statics.Bulk_PostText_Updates) == 0:
                return

            try:
                await MongoDBAsync.post_data.bulk_write(statics.Bulk_PostText_Updates, ordered=False)
            except BulkWriteError as ex:
                print("Error on BulkWrite for post_text:")
                print(ex)
            statics.Bulk_PostText_Updates = []

        # Do all updates
        await asyncio.wait([doPostDataUpdate(), doPostTextUpdate(), perform_amabledb_inserts()])
            
        # Wait a bit (if tasks was not full ==> relax CPU)
        print(f"Tasks ran: {len(tasks)}")   
        if len(tasks) >= BATCH_SIZE:
            await asyncio.sleep(60)

def start() -> None:
    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(run())
    event_loop.close()

if __name__ == '__main__':
   start()