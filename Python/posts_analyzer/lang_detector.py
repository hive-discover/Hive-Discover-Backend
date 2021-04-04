import time
import sys, os
from typing import Generator
sys.path.append(os.getcwd() + "/.")

from pymongo import UpdateMany
from pymongo.errors import BulkWriteError

from database import MongoDB, MongoDBAsync
from helper import helper, Lemmatizer
from network import LangDetector


def load_models() -> tuple:
    '''Load LangDetector and Lemmatizer and return both in a tuple'''
    return (LangDetector(load_model=True), Lemmatizer())   

def detect_lang(post : dict, lang_detector : LangDetector, lmtz : Lemmatizer) -> list:
    '''Detect langs and return it'''
    text = ""
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


def run() -> None:
    '''Main Function: Runs endless to detect all langs'''
    lang_detector, lmtz = load_models()
    MongoDB.init_global(post_table=True)
    helper.init()

    current_post = None
    posts, bulk_updates = [], []
    while 1:
        # Get Posts
        for current_post in MongoDB.post_data.find({"lang" : None}):
            posts.append(current_post)

            if len(posts) > 100:
                break
        
        # Nothing is do to
        if len(posts) == 0:
            time.sleep(10)
            continue

        # Get Text
        for current_post in MongoDB.post_text.find({"_id" : {"$in" : [p["_id"] for p in posts]}}):
            for index, post in enumerate(posts):
                if post["_id"] == current_post["_id"]:
                    posts[index] = {**post, **current_post}

        # Get langs   
        for p in posts:
            lang = detect_lang(p, lang_detector, lmtz)
            bulk_updates.append(UpdateMany({"_id" : p["_id"]}, {"$set" : {"lang" : lang}}))
        
        # Do changes
        if len(bulk_updates) > 0:
            try:
                MongoDB.post_data.bulk_write(bulk_updates, ordered=False)
            except BulkWriteError:
                pass

        # Reset        
        posts, bulk_updates = [], []
        time.sleep(0.1)

        




def start() -> None:
    run()

if __name__ == '__main__':
   start()

