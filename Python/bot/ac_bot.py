import time
import random
import requests
import json

from datetime import datetime, timedelta
import sys, os
sys.path.append(os.getcwd() + "/.")

from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Vote

from config import *
from database import MongoDB

API_URL = "https://api.hive-discover.tech"

SEARCH_QUERIES = [
    "art", "beer", "linux", "hive", "world", "soccer",
    "covid-19", "germany", "hive discvoer", "computer", 
    "steemit", "technology", "ai", "coding", "football",
    "vs code", "python", "docker", "sport"
    ]
_ = [[SEARCH_QUERIES.append(tag) for tag in label] for label in CATEGORIES]

SEARCH_SORTINGS = [
        {
            "type": "personalized",
            "account": {
            "name": "ac-bot",
            "access_token": "ac-bot-test-access-token"
            }
        },
        "latest", 
        "oldest"
]

def vote_on_content(author : str, permlink : str) -> bool:
    '''Vote on a Post. Returns True if successful, else False'''
    print(f"Voting on one Post: @{author}/{permlink}.")

    # Building Vote-Op
    tx = TransactionBuilder(blockchain_instance=Hive())
    tx.appendOps(Vote(**{
        "voter": "ac-bot",
        "author": author,
        "permlink": permlink,
        "weight": 10
    }))

    try:
        # Trying to send Vote
        tx.appendWif(AC_BOT_POSTING_WIF)
        signed_tx = tx.sign()
        broadcast_tx = tx.broadcast(trx_id=True)
        print("Cast was successfull: " + str(broadcast_tx))
        return True
    except Exception as ex:
        # Failed
        print("Cast was NOT successfull: ")
        print(ex)

    return False

def do_search_request():  
    # Create random search payload
    payload = json.dumps({
        "query": { "text": random.choice(SEARCH_QUERIES) },
        "sort": random.choice(SEARCH_SORTINGS),
        "amount": random.randint(25, 100),
        "full_data": True
    })

    # Make request
    start_time = time.time()
    response = requests.request(
        "POST", 
        API_URL + "/search/posts", 
        headers={ 'Content-Type': 'application/json' }, 
        data=payload
    )
    search_result = json.loads(response.text)
    print(f"Did Search request in {time.time() - start_time}s")
    return

def getAcBot_ID() -> int:
    doc = MongoDB.account_info.find_one({"name" : "ac-bot"})
    return doc["_id"]

def life():
    '''Endless Method to create bot-behaviour. Can have long waiting periods...'''
    ac_bot_id = getAcBot_ID()

    while 1:
        # Search for something
        do_search_request()

        # Check vote count in the last 5 days
        min_date = datetime.utcnow() - timedelta(days=5)
        vote_count = MongoDB.post_data.count_documents({"votes" : ac_bot_id, "timestamp" : {"$gte" : min_date}})
        if vote_count >= AC_BOT_VOTE_COUNT:
            # Enough Votes, just wait 5 Minutes and continue
            time.sleep(60 * 5)
            continue

        # Not enough Votes ==> Find random Posts and vote them    
        query = {"votes" : {"$ne" : ac_bot_id}, "timestamp" : {"$gte" : min_date}}
        doc_count = MongoDB.post_data.count_documents(query)

        # Get random ones (3)
        for post_data in MongoDB.post_data.find(query).skip(random.randint(0, doc_count)).limit(3):
            # Get authorperm
            post_info = MongoDB.post_info.find_one({"_id" : post_data["_id"]})
            if not post_info: # Some Error
                continue

            # Vote on Post and wait a minute
            vote_on_content(post_info["author"], post_info["permlink"])
            time.sleep(60)



def start():
    '''Starting the AC-Bot. (Endless Thread)'''
    MongoDB.init_global(post_table=True, account_table=True, stats_table=True)
    life()
    

if __name__ == '__main__':
    start()