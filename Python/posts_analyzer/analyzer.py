import asyncio
import time
import sys, os
from typing import Awaitable
sys.path.append(os.getcwd() + "/.")

import torch as T

from config import *
from helper import helper
from database import MongoDBAsync

class statics:
    FASTTEXT_MODEL = None
    LANG_DETECTOR = None
    TEXT_CNN = None
    LMZT = None

async def detect_lang(post : dict) -> None:
    '''Detect a Language and insert it into DB'''
    text = ""
    if "title" in post:
        text += post["title"] + ". "
    if "body" in post:
        text += post["body"] + ". "

    if len(text.split(' ')) > 2:
        text = helper.pre_process_text(text, lmtz=statics.LMZT)
        lang = statics.LANG_DETECTOR.predict_lang(text)
    else:
        lang = []

    await MongoDBAsync.post_table.update_many({"post_id" : post["post_id"]}, {"$set" : {"lang" : lang}})

async def categorize_post(post : dict) -> None:
    '''Categorize a post based on TextCNN and update post in DB'''
    # Prepare Text
    text = ""
    if "title" in post:
        text += post["title"] + ". "
    if "body" in post:
        text += post["body"] + ". "
    if "tags" in post:
        text += post["tags"]
    text = helper.pre_process_text(text, lmtz=statics.LMZT)
    tok_text = helper.tokenize_text(text)
    
    # Calc word vectors
    vectors = []
    for word in tok_text:
        try:
            vectors.append(statics.FASTTEXT_MODEL.wv[word])
        except:
            pass
    
    if len(vectors) < MIN_KNOWN_WORDS:
        # Not enough words
        categories = False
    else:
        # DO AI
        _input = T.Tensor([vectors]) # [Batch-Dim, Word, Vectors]
        _output = statics.TEXT_CNN(_input) # [Batch-Dim, Categories] 
        categories = _output.data[0].tolist()

    await MongoDBAsync.post_table.update_many({"post_id" : post["post_id"]}, {"$set" : {"categories_doc" : categories}})

def load_models():
    from gensim.models import KeyedVectors 
    from network import TextCNN, LangDetector
    from agents import Lemmatizer

    statics.TEXT_CNN, loaded = TextCNN.load_model()
    statics.FASTTEXT_MODEL = KeyedVectors.load(FASTTEXT_MODEL_PATH)
    statics.LANG_DETECTOR = LangDetector(load_model=True)   
    print(f"Loaded TextCNN from Disk: {loaded}")
    statics.LMZT = Lemmatizer()

async def run():
    '''Analyze everything'''
    MongoDBAsync.init_global(post_table=True)
    load_models()
    helper.init()

    while 1:
        # 1. Analyze Language
        tasks = []
        async for post in MongoDBAsync.post_table.find({"lang" : None}):
            tasks.append(detect_lang(post))

            # Prevent Overflow
            if len(tasks) > 50:
                break

        # 2. Anaylze Categories
        async for post in MongoDBAsync.post_table.find({"categories_doc" : None}):
            tasks.append(categorize_post(post))

            # Prevent Overflow
            if len(tasks) > 100:
                break
            
        if len(tasks) > 0:
            await asyncio.wait(tasks)
        else:
            await asyncio.sleep(3)
        


def start_analyzer():
    asyncio.run(run())

if __name__ == '__main__':
   start_analyzer()

