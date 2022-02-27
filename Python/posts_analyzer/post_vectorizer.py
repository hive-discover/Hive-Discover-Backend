import asyncio

import motor.motor_asyncio
import numpy as np
from pymongo import UpdateOne

import time
import sys, os
sys.path.append(os.getcwd() + "/.")

from config import *

FIND_NATIVE_AGG_PIPELINE = [
    {
        "$match" : {
            "lang.lang" : {"$in" : ["en", "es", "de"]},
            "$or" : [
                {"doc_vectors" : {"$exists" : False}},
                {"doc_vectors" : None},
                {"doc_vectors" : {}},
                {"re_vectorize" : True}
            ]
        }
    },{
        "$sample" : {"size" : 25}
    },{
        "$project" : {"_id" : 1}
    }      
]

FIND_STOCK_AGG_PIPELINE = [
    {
        "$match" : {
            "$or" : [
                {"doc_vectors" : {"$exists" : False}},
                {"doc_vectors" : None},
                {"re_vectorize" : True}
            ]
        }
    },{
        "$sample" : {"size" : 25}
    },{
        "$project" : {"_id" : 1}
    }      
]

mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_CONNECTION_STR)

def preprocess_text(text : str) -> str:
    text = text.replace(".", " . ").replace(",", " , ").replace("\n", " \n ")
    text = text.replace(")", " ) ").replace("(", " ( ")
    text = text.replace("$", " $ ").replace("%", " % ").replace("#", " # ").replace("@", " @ ")
    text = text.replace("!", " ! ").replace("?", " ? ").replace(";", " ; ").replace(":", " : ")
    text = text.replace("\"", " \" ").replace("\'", " \' ").replace("\\", " \\ ").replace("/", " / ")
    text = text.replace("-", " - ").replace("_", " _ ").replace("+", " + ").replace("=", " = ")
    text = text.replace("*", " * ").replace("^", " ^ ").replace("&", " & ").replace("|", " | ")
    text = text.replace("<", " < ").replace(">", " > ").replace("~", " ~ ").replace("`", " ` ")
    text = text.replace("[", " [ ").replace("]", " ] ").replace("{", " { ").replace("}", " } ")
    text = text.replace("'", " ' ").replace("\"", " \" ")
    return text.lower()

async def get_tokens(post_id : int, image_api = False) -> tuple:
    # Get post from database, then preprocess and tokenize it
    if not image_api:
        # General Post from the Blockchain
        text_doc = await mongo_client["hive-discover"]["post_text"].find_one({'_id': post_id})
        text = text_doc['title'] + " " + text_doc['body']
    else:
        # Hive Stock Image Post
        text_doc = await mongo_client["images"]["post_text"].find_one({'_id': post_id})
        text = text_doc["text"].replace("\n", " ").replace("-", " ").replace("_", " ").replace("+", " ").replace("&", " ")

    # Tokenize
    text = preprocess_text(text)
    all_tokens = text.split()
    unique_tokens = list(set(all_tokens))
    return (all_tokens, unique_tokens)

async def init_matrices(post_id : int, unique_tokens : list, image_api=False) -> tuple:
    # Init tf- and idf-matrices
    lang_tf_matrix = {} # { "en" : {tokene1 : counte1}, "ru" : {tokene1 : counte1} }"}
    lang_idf_matrix = {}# { "en" : {tokene1 : idf1e}, "ru" : {tokene1 : idf1} }"}

    if not image_api:
        # Get post-langs from a native-post
        post_langs = await mongo_client["hive-discover"]["post_data"].find_one({'_id': post_id}, projection={"lang" : 1})
        if not post_langs or not post_langs["lang"]: # No Lang was calculated
            return ({}, {})

        post_langs = post_langs["lang"] # [{lang : en, x : 0.4}, {lang : ru, x : 0.6}]
        post_langs = [item["lang"] for item in post_langs]
    else:
        # ImageAPI only supports english content
        post_langs = ["en"]

    # Fill lists with zeros and idf-scores
    for lang in await mongo_client["fasttext"].list_collection_names():
        if lang not in post_langs:
            continue # Skip languages not in post-langs

        async for doc in mongo_client["fasttext"][lang].find({"_id" : {"$in" : unique_tokens}}, projection={"v" : 0}):
            if lang not in lang_idf_matrix:
                # First item of that lang
                lang_tf_matrix[lang] = {}
                lang_idf_matrix[lang] = {}

            lang_tf_matrix[lang][doc['_id']] = 0
           # if not image_api:
            lang_idf_matrix[lang][doc['_id']] = doc['idf']
            #else:
           #     lang_idf_matrix[lang][doc['_id']] = doc['img_idf']


    return (lang_tf_matrix, lang_idf_matrix)

async def calc_tf_idf_scores(post_id : int, image_api=False) -> dict:
    all_tokens, unique_tokens = await get_tokens(post_id, image_api)

    # Init tf- and idf-matrices
    lang_tf_matrix = {} # { "en" : {tokene1 : counte1}, "ru" : {tokene1 : counte1r} }"}
    lang_idf_matrix = {} # { "en" : {tokene1 : idf1e}, "ru" : {tokene1 : idf1r} }"}
    lang_tf_matrix, lang_idf_matrix = await init_matrices(post_id, unique_tokens, image_api)

    # Count term-frequency for each token and for each language
    known_token_count = {} # {"en" : 0, "ru", 0}
    for token in all_tokens:
        for lang in lang_tf_matrix.keys():
            if lang not in known_token_count: # Add entry for that lang
                known_token_count[lang] = 0

            if token in lang_tf_matrix[lang]: # Check token
                lang_tf_matrix[lang][token] += 1
                known_token_count[lang] += 1

    # Calculate tf-idf combined for each token and for each language
    # tf(t) = n(t) / known_tokens(lang)
    # x = tf(t) * idf(t)
    for lang in lang_tf_matrix.keys():
        for token in lang_tf_matrix[lang].keys():
            lang_tf_matrix[lang][token] = (lang_tf_matrix[lang][token] / known_token_count[lang]) * lang_idf_matrix[lang][token]

    # Weight word-vectors with tf-idf score and add all for every lang
    lang_weighted_vectors = {} # {lang : weighed vector (np array)}
    for lang in lang_tf_matrix.keys():
        # Find vector for this lang and this post
        post_vectors = {} # {token (str) : vector (np array)}
        async for document in  mongo_client["fasttext"][lang].find({"_id" : {"$in" : unique_tokens}}):
            # Also decode base64
            post_vectors[document['_id']] = np.frombuffer(document['v'], dtype=np.float32)

        # Calculate weighted vectors
        lang_weighted_vectors[lang] = np.zeros(300, dtype=np.float32)
        for token in all_tokens:
            if token not in post_vectors:
                continue # not this language
        
            # Add weighted vector
            lang_weighted_vectors[lang] += post_vectors[token] * lang_tf_matrix[lang][token]

    return lang_weighted_vectors

async def process_one_native_post(post_id: int) -> UpdateOne:    
    lang_weighted_vectors = await calc_tf_idf_scores(post_id, image_api=False)   

    # Get binary from np.array
    for lang in lang_weighted_vectors.keys():
        lang_weighted_vectors[lang] = lang_weighted_vectors[lang].tobytes()

    update = {
        "$set" : {
            "doc_vectors" : lang_weighted_vectors
        },
        "$unset" : {
            "re_vectorize" : ""
        }
    }
    return UpdateOne({"_id" : post_id}, update)

async def process_one_stock_post(post_id: int) -> UpdateOne:    
    lang_weighted_vectors = await calc_tf_idf_scores(post_id, image_api=True)   

    # Get binary from np.array
    if "en" in lang_weighted_vectors: # english-content exists
        lang_weighted_vectors = lang_weighted_vectors["en"].tobytes()
    else: # set it to false
        lang_weighted_vectors = False

    update = {
        "$set" : {
            "doc_vectors" : lang_weighted_vectors
        },
        "$unset" : {
            "re_vectorize" : ""
        }
    }
    return UpdateOne({"_id" : post_id}, update)


async def manage_native_posts() -> None:
    # Find native posts where work is needed
    tasks = []
    async for post_id in mongo_client["hive-discover"]["post_data"].aggregate(FIND_NATIVE_AGG_PIPELINE):   
        tasks.append(process_one_native_post(post_id["_id"]))

    if len(tasks) == 0:
        return 0

    # Update posts
    bulk_update = await asyncio.gather(*tasks)
    bulk_update = [x for x in bulk_update if x] # Remove None's
    if len(bulk_update) > 0:
        await mongo_client["hive-discover"]["post_data"].bulk_write(bulk_update, ordered=False)

    # Logging
    print(f"[INFO] Vectorized {len(tasks)} native-posts")
    return len(tasks)

async def manage_stock_posts() -> None:
    # Find stock posts where work is needed
    tasks = []
    async for post_id in mongo_client["images"]["post_text"].aggregate(FIND_STOCK_AGG_PIPELINE):   
        tasks.append(process_one_stock_post(post_id["_id"]))

    if len(tasks) == 0:
        return 0

    # Update posts
    bulk_update = await asyncio.gather(*tasks)
    bulk_update = [x for x in bulk_update if x] # Remove None's
    if len(bulk_update) > 0:
        await mongo_client["images"]["post_text"].bulk_write(bulk_update, ordered=False)

    # Logging
    print(f"[INFO] Vectorized {len(tasks)} stock-posts")
    return len(tasks)

async def main() -> None: 
    while 1:
        post_count, start_time = 0, time.time()
        
        # Do work and send heartbeat
        post_count += await manage_native_posts()
        post_count += await manage_stock_posts()

        # Send hearbeat
        elapsed_time = (time.time() - start_time) * 1000
        do_heartbeat("VECTORIZER", params={"msg" : "OK", "ping" : elapsed_time})
        
        # wait when nothing were done
        if post_count == 0:
            await asyncio.sleep(10)


def start()->None:
    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(main())
    event_loop.close()

if __name__ == '__main__':
    start()
