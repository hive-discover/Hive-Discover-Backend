import config as conf
import network

from beem import Hive
from beem.account import Account
from beem.comment import Comment
from beem.exceptions import ContentDoesNotExistsException
from beem.vote import AccountVotes
import  numpy as np
import torch as T
import json
import urllib.request
import os
import re

def get_website_code(url : str):    
    try:
        headers = {'User-Agent':conf.USER_AGENT,} 
        request = urllib.request.Request(url, None, headers) 
        response = urllib.request.urlopen(request)
        data = response.read() 

        return data.decode()
    except Exception as e:
        print("Failed to get website code! Url: " + url)
        print(e)
        return ''

# ---   HIVE   ---
def get_hive_post_json(url : str):
    # Header is needed. Else they 
    # return a 403 Code (Forbidden)
    headers = {'User-Agent':conf.USER_AGENT,} 

    try:
        request = urllib.request.Request(url, None, headers) 
        response = urllib.request.urlopen(request)
        data = response.read() 
    except Exception as e:
        print("Failed reading Post json! Url: " + url)
        print(e)
        return json.loads('{"body":""}')

    # return only the post element
    try:
        return json.loads(data.decode())['post']
    except Exception as e:
        print("Can't get " + url)
        print(e)
        return json.loads('{"body":""}')

def get_all_hive_posts(author : str):
    account = Account(author)
    c_list = {}
    posts = [] # (permlink, author)
    
    for post in account.blog_history():
        if post["parent_author"] is '':
            # only posts, no comments
            posts.append((post["permlink"], post["author"]))

    return posts

def get_all_hive_votes(author : str):
    votes = AccountVotes(author)
    posts = [] # (permlink, author)
    for vote in votes:
        posts.append((vote["permlink"], vote["author"]))
    return posts

def get_hive_post(permlink : str, author : str):    
    c = Comment(f'@{author}/{permlink}', blockchain_instance=Hive(conf.HIVE_NODES[np.random.randint(0, len(conf.HIVE_NODES))]))
    return c

def load_train_dataset_file():
    if os.path.exists(conf.TRAINING_DATASET_PATH) == False:
        print("[FAILED] Training dataset file is not available. Please make one!")
        return []

    with open(conf.TRAINING_DATASET_PATH, 'r') as file:
        dataset = json.load(file)

    print(f"[INFO] Loaded training dataset with {len(dataset)} items.")
    return dataset

def load_test_dataset_file():
    if os.path.exists(conf.TEST_DATASET_PATH) == False:
        print("[FAILED] Testing dataset file is not available. Please make one!")
        return []

    with open(conf.TEST_DATASET_PATH, 'r') as file:
        dataset = json.load(file)

    print(f"[INFO] Loaded test dataset with {len(dataset)} items.")
    return dataset

def pre_process_text(text : str):
    # remove all Links
    text = re.sub(r'^https?:\/\/.*[\r\n]*', ' ', text, flags=re.MULTILINE)  # Remove simple Links
    text = re.sub(r'[\(\[].*?[\)\]]', ' ', text, flags=re.MULTILINE) # Remove Markdown for Images and Links

    # replace some Characters
    text = text.replace('?', '.').replace('!', '.')
    text = text.replace('\n', '')
    text = text.replace('#', '').replace('-', '')
    text = text.replace("'", ' ').replace(", ", ' ').replace(':', '.').replace(';', ' ')
    text = text.replace('$ ', ' Dollar ').replace(' $', ' Dollar ')
    text = text.replace('€ ', ' Dollar ').replace(' €', ' Dollar ')
    text = text.replace('%', " percentage ")
    while '  ' in text:
        text = text.replace('  ', ' ')

    text = text.replace(' .', '.')
    while '..' in text:
        text = text.replace('..', '.')

    

    return text.lower()



