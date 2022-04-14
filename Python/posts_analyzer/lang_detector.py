import time
import sys, os
sys.path.append(os.getcwd() + "/.")

from pymongo import UpdateOne

from database import MongoDB
from helper import helper, Lemmatizer
from network import LangDetector
from config import *

# load both models
lang_detector, lmtz = (LangDetector(load_model=True), Lemmatizer())

os_client = get_opensearch_client()

def detect_lang(post : dict, lang_detector : LangDetector, lmtz : Lemmatizer) -> list:
    '''Detect langs and return it'''
    text = ""
    if "text" in post:
        text += post["text"] + ". "
    if "title" in post:
        text += post["title"] + ". "
    if "body" in post:
        text += post["body"] + ". "

    if len(text.split(' ')) > 2:
        text = helper.pre_process_text(text, lmtz=lmtz)
        lang = lang_detector.predict_lang(text)
    else:
        lang = []
    return lang

def get_for_nativeposts() -> int:
    # Get Ids to work on
    posts = [p for p in MongoDB.post_data.find({"$or" : [{"lang" : None}, {"lang" : {"$exists" : False}}]}, projection={"_id" :1}).limit(100)]
    
    # Get Text and Lang for each _id
    mongo_bulk_updates = []
    opensearch_bulk_updates = []
    for current_post in MongoDB.post_text.find({"_id" : {"$in" : [p["_id"] for p in posts]}}):
        lang = detect_lang(current_post, lang_detector, lmtz)
        mongo_bulk_updates.append(UpdateOne({"_id" : current_post["_id"]}, {"$set" : {"lang" : lang}}))

        opensearch_bulk_updates.append({ "update" : { "_index": "hive-post-data", "_id" : current_post["_id"] }})
        opensearch_bulk_updates.append({ "doc" : { "language" : lang }})


    # Do changes
    if len(mongo_bulk_updates) > 0:
        MongoDB.post_data.bulk_write(mongo_bulk_updates, ordered=False)
    if len(opensearch_bulk_updates) > 0:
        os_client.bulk(body=opensearch_bulk_updates, index="hive-post-data")

    return len(mongo_bulk_updates)

def get_for_stockcomments():
    bulk_updates = []

    # Go through an amount of unprocessed stockcomments
    for comment in MongoDB.mongo_client["images"].post_replies.find({"$or" : [{"lang" : None}, {"lang" : {"$exists" : False}}]}).limit(100):
        lang = detect_lang(comment, lang_detector, lmtz)
        bulk_updates.append(UpdateOne({"_id" : comment["_id"]}, {"$set" : {"lang" : lang}}))

    # Do changes
    if len(bulk_updates) > 0:
        MongoDB.mongo_client["images"].post_replies.bulk_write(bulk_updates, ordered=False)

    return len(bulk_updates)

def get_for_replies() -> int:   
    # Get Text
    bulk_updates = []
    for current_post in MongoDB.post_replies.find({"$or" : [{"lang" : None}, {"lang" : {"$exists" : False}}]}).limit(100):
        lang = detect_lang(current_post, lang_detector, lmtz)
        bulk_updates.append(UpdateOne({"_id" : current_post["_id"]}, {"$set" : {"lang" : lang}}))

    # Do changes
    if len(bulk_updates) > 0:
        MongoDB.post_replies.bulk_write(bulk_updates, ordered=False)

    return len(bulk_updates)

def run() -> None:
    '''Main Function: Runs endless to detect all langs'''
    MongoDB.init_global(post_table=True)
    helper.init()

    while 1:
        counter, start_time = 0, time.time()
        counter += get_for_nativeposts()
        counter += get_for_stockcomments()
        counter += get_for_replies()

        # Send heartbeat
        elapsed_time = (time.time() - start_time) * 1000
        payload = {'msg': 'OK', 'ping' : elapsed_time}        
        do_heartbeat("LANG_DETECTOR", params=payload)    

        if counter == 0:
            time.sleep(10)   
        else:
            print(f"[INFO] Detected langs for {counter} posts in {elapsed_time}ms")   




def start() -> None:
    run()

if __name__ == '__main__':
   start()

