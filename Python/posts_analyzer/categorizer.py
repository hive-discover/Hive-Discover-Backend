import time
import sys, os
sys.path.append(os.getcwd() + "/.")

import torch as T
from gensim.models import KeyedVectors

from pymongo.errors import BulkWriteError
from pymongo import UpdateMany

import nltk
from nltk.corpus import stopwords

from network import TextCNN
from config import *
from helper import helper, Lemmatizer
from database import MongoDB

def load_models() -> tuple:
    '''Load TextCnn, Fasttext model and lmtz and return both in a tuple'''
    TEXT_CNN, loaded = TextCNN.load_model()
    FASTTEXT_MODEL = KeyedVectors.load(FASTTEXT_MODEL_PATH)
    LMZT = Lemmatizer()

    print(f"Loaded TextCNN from Disk? - {loaded}")
    return (TEXT_CNN, FASTTEXT_MODEL, LMZT)   

def categorize_post(post : dict, TEXT_CNN : TextCNN, FASTTEXT_MODEL : KeyedVectors, LMZT : Lemmatizer) -> list:
    '''Categorize one post and return categories'''
    # Prepare Text
    text = ""
    if "title" in post:
        text += post["title"] + ". "
    if "body" in post:
        text += post["body"] + ". "
    if "tags" in post:
        text += post["tags"]
    text = helper.pre_process_text(text, lmtz=LMZT)
    tok_text = helper.tokenize_text(text)
    
    # Calc word vectors
    vectors = []
    for word in tok_text:
        try:
            vectors.append(FASTTEXT_MODEL.wv[word])
        except:
            pass
    
    if len(vectors) < MIN_KNOWN_WORDS:
        # Not enough words
        categories = False
    else:
        # DO AI
        _input = T.Tensor([vectors]) # [Batch-Dim, Word, Vectors]
        _output = TEXT_CNN(_input) # [Batch-Dim, Categories] 
        categories = _output.data[0].tolist()

    return categories

def remove_stop_duplicate_words(body : str) -> str:
    '''Remove all stopwords and duplicate words'''
    if body:
        filtered_words = [word for word in body.split(' ') if word not in stopwords.words("english")]
        filtered_words = list(dict.fromkeys(filtered_words))

        # Return as str
        return ' '.join(filtered_words)
    
    return ""

def run() -> None:
    '''Main Function: Runs endless to categorize all posts'''
    nltk.download("stopwords")
    TEXT_CNN, FASTTEXT_MODEL, LMZT = load_models()
    MongoDB.init_global(post_table=True)
    helper.init()

    current_post, cats = None, None
    posts, bulk_updates_data, bulk_updates_text = [], [], []
    while 1:
        # Get Posts
        for current_post in MongoDB.post_data.find({"categories" : None}):   
            posts.append(current_post)

            if len(posts) > 20:
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

        for p in posts:
            cats = categorize_post(p, TEXT_CNN, FASTTEXT_MODEL, LMZT)
            bulk_updates_data.append(UpdateMany({"_id" : p["_id"]}, {"$set" : {"categories" : cats}}))

            if "body" in p and "title" in p:
                new_body = remove_stop_duplicate_words(p["body"])
                new_title = remove_stop_duplicate_words(p["title"])
                bulk_updates_text.append(UpdateMany({"_id" : p["_id"]}, {"$set" : {"body" : new_body, "title" : new_title}}))
        
        # Do changes
        if len(bulk_updates_data) > 0:
            try:
                MongoDB.post_data.bulk_write(bulk_updates_data, ordered=False)
            except BulkWriteError:
                pass
        if len(bulk_updates_text) > 0:
            try:
                MongoDB.post_text.bulk_write(bulk_updates_text, ordered=False)
            except BulkWriteError:
                pass

        # Reset 
        print(f"Updated: {len(posts)}")       
        posts, bulk_updates_data, bulk_updates_text = [], [], []
        time.sleep(0.1)




def start() -> None:
    run()

if __name__ == '__main__':
   start()