import time
import random
from datetime import datetime, timedelta
import sys, os
sys.path.append(os.getcwd() + "/.")

from beem import Hive
from beem.transactionbuilder import TransactionBuilder
from beembase.operations import Vote

from config import *
from database import MongoDB

def vote_on_content(author : str, permlink : str) -> bool:
    '''Vote on a Post. Returns True if successful, else False'''
    print(f"Voting on one Post: @{author}/{permlink}.")

    # Building Vote-Op
    tx = TransactionBuilder(blockchain_instance=Hive())
    tx.appendOps(Vote(**{
        "voter": "ac-bot",
        "author": author,
        "permlink": permlink,
        "weight": int(float(1) * 100)
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

def getAcBot_ID() -> int:
    doc = MongoDB.account_info.find_one({"name" : "ac-bot"})
    return doc["_id"]

def life():
    '''Endless Method to create bot-behaviour. Can have long waiting periods...'''
    ac_bot_id = getAcBot_ID()

    while 1:
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
    MongoDB.init_global(post_table=True, account_table=True)
    life()
    

