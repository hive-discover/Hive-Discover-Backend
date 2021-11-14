import asyncio, time
import json
import math
import requests
from datetime import timezone, timedelta, datetime
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

from network import TextCNN, FakeNewsCNN
from config import *
from helper import helper, Lemmatizer
from database import MongoDBAsync

class statics:
    TEXT_CNN : TextCNN = None
    FAKENEWS_CNN : FakeNewsCNN = None
    LMZT : Lemmatizer = None
    Unknown_Tokens : list = []
    Bulk_PostData_Updates : list = []
    Bulk_PostText_Updates : list = []


        
# Inits  
def load_models() -> None:
    '''Load TextCnn and lmtz'''
    statics.TEXT_CNN, loaded = TextCNN.load_model()
    print(f"Loaded TextCNN from Disk? - {loaded}")

    statics.FAKENEWS_CNN, loaded = FakeNewsCNN.load_model()
    print(f"Loaded FakeNewsCNN from Disk? - {loaded}")

    statics.LMZT = Lemmatizer()
    
async def get_unknown_tokens() -> None:
    vectors = await get_word_vectors(["(", "unknown", ")"])
    statics.Unknown_Tokens = [vectors["("], vectors["unknown"], vectors[")"]]


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

    # Decode vector map
    for word in server_vectors.keys():
        d_bytes = base64.b64decode(server_vectors[word])
        server_vectors[word] = np.frombuffer(d_bytes, dtype=np.float64)

    return server_vectors

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
    vector_map = await get_word_vectors(tok_text)

    doc_vector = []
    vectors = []

    # Transform vector map to an ordered list word by word + unknown tokens
    known_tokens, unknown_tokens = 0, 0
    for word in tok_text:
        if word in vector_map:
            # Known Token
            vectors.append(vector_map[word])
            doc_vector.append(vector_map[word])
            known_tokens += 1
        else:
            # Unknown Token
            vectors += statics.Unknown_Tokens
            unknown_tokens += 1
    
    # Calc doc_vector by summing all known tokens and calc average
    doc_vector = (np.sum(doc_vector, axis=0) / known_tokens).tolist()
 
    if len(vectors) < MIN_KNOWN_WORDS:
        # Not enough words
        categories = False
        fakenews_prob = False
    else:
        # Calculate categories
        _input = T.Tensor([vectors]) # _input.shape = [Batch-Dim, Word, Vectors]
        _output = statics.TEXT_CNN(_input) # _output.shape = [Batch-Dim, Categories] 
        categories = _output.data[0].tolist()
            

        # Calculate fakenews_prob
        _input = T.Tensor([vectors]) # _input.shape = [Batch-Dim, Word, Vectors]
        _output = statics.FAKENEWS_CNN(_input) 
        fakenews_prob = _output.data[0].tolist()[0] # fakenews = [1, 0] | realnews = [0, 1]


    # post_data Update
    statics.Bulk_PostData_Updates.append(
        UpdateOne({"_id" : post["_id"]}, {"$set" : {
            "categories" : categories, 
            "doc_vector" : doc_vector, 
            "fakenews_prob" : fakenews_prob,
            "tokens" : { "known" : known_tokens, "unknown" : unknown_tokens }
            }
        })
    )


async def run(BATCH_SIZE : int = 25) -> None:
    # Init
    nltk.download("stopwords")
    load_models()
    MongoDBAsync.init_global(post_table=True)

    await get_unknown_tokens()  
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
                await MongoDBAsync.post_text.bulk_write(statics.Bulk_PostText_Updates, ordered=False)
            except BulkWriteError as ex:
                print("Error on BulkWrite for post_text:")
                print(ex)
            statics.Bulk_PostText_Updates = []

        # Do all updates
        await asyncio.wait([doPostDataUpdate(), doPostTextUpdate()])
            
        # Wait a bit (if tasks was not full ==> relax CPU and repair)
        print(f"Tasks ran: {len(tasks)}")   
        if len(tasks) < BATCH_SIZE:
            await asyncio.sleep(60)
            

def start() -> None:
    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(run())
    event_loop.close()

if __name__ == '__main__':
   start()