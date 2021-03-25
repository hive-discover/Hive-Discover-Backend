import asyncio
import pymongo
import secrets
import os, sys, time
sys.path.append(os.getcwd() + "/.")

from pymongo import UpdateMany
from pymongo.errors import BulkWriteError

from account_processing import get_account_cats_langs
from database import MongoDBAsync
from agents import PostsCategory
from hive import AccountsManager
from config import *
 
currently_makings = [] # account_names
open_db_updates = [] 

async def do_feed(account_id : int, stop_event, delete_old = False):
    global open_db_updates
    # Remove request and Lock account
    open_db_updates.append(UpdateMany({"_id" : account_id}, {"$unset" : {"make_feed" : ""}}))
    if account_id in currently_makings:
        return
    currently_makings.append(account_id)

    acc_langs = []
    last_posts_count, last_votes_count, counter = 0, 0, 0
    acc, acc_posts, acc_votes = None, None, None
    feed_list, similar_posts = [], []

    account_info = await MongoDBAsync.account_info.find_one({"_id" : account_id})
    while stop_event is None or not stop_event.is_set():
        acc = await MongoDBAsync.account_data.find_one({"_id" : account_id})
        if not acc:
            # no account -> something went wrong
            break

        if "loading" not in acc:
            # Put analyze request into DB and wait a bit
            open_db_updates.append(UpdateMany({"_id" : account_id}, {"$set" : {"analyze" : True}}))
            await asyncio.sleep(1)
            continue
        

        # Get Lang from Account as a simple List. From [{...}, {...}] to ["...", "..."]
        _, acc_langs = await get_account_cats_langs(account_id=account_id)
        acc_langs = [item["label"] for item in acc_langs]

        if not "feed" in acc:
            # Setup, only local
            acc["feed"] = []

        if len(acc["feed"]) >= ACCOUNT_MIN_FEED_LEN and delete_old is False:
            # Succes, feed_list is full
            break
        
        # Prepare ids
        own_post_ids = [post["_id"] async for post in MongoDBAsync.post_info.find({"author" : account_info["name"]})]
        vote_post_ids = [post["_id"] async for post in MongoDBAsync.post_data.find({"votes" : account_id})]

        # Get Post Ids (similar)    
        if len(own_post_ids) > 0:
            # Get similar posts like his own
            search_results = await PostsCategory.search(own_post_ids, k=(15 + counter * 2))
            similar_posts += search_results["results"]
            
        if len(vote_post_ids) > 0:
            # Get similar posts like he voted
            search_results = await PostsCategory.search(vote_post_ids, k=(10 + counter * 2))
            similar_posts += search_results["results"]

        # Incrementing the counter var to get more posts when it is running a long time
        # Prevents, that nothing will be found
        counter += 1

        # Extrace Similar Post IDs
        open_ids = []
        for item in similar_posts:
            # Enter all in open_ids
            open_ids += [result["_id"] for result in item["results"]]

        # Check if not liked or not own posts
        for _id in open_ids:
            if _id in vote_post_ids or _id in own_post_ids:
                open_ids.remove(_id)

        # Check langs from the posts: Query for id and lang (it will only return matches)
        find_cursor = MongoDBAsync.post_data.find({"_id" : {"$in" : open_ids}, "lang" : {"$elemMatch" : {"lang" : {"$in" : acc_langs}}}})
        open_ids = [post["_id"] async for post in find_cursor]

        # Choose randoms to fill the amount
        amount = min(len(open_ids), ACCOUNT_MIN_FEED_LEN - len(acc["feed"]))
        open_ids = [secrets.choice(open_ids) for _ in range(amount)]

        # Enter them
        if len(open_ids) > 0:
            if delete_old:
                await MongoDBAsync.account_data.update_many({"_id" : account_id}, {"$set" : {"feed" : []}})
                delete_old = False        
            open_db_updates.append(UpdateMany({"_id" : account_id}, {"$addToSet" : {"feed" : {"$each" : open_ids}}}))    
        
        # wait
        await asyncio.sleep(0.5)

    currently_makings.remove(account_id)
 
async def run(stop_event = None):
    '''Endless Loop: Runner for this Process'''
    global open_db_updates
    MongoDBAsync.init_global(post_table = True, account_table = True, banned_table = True)
    await PostsCategory.create_search_index()
    last_search_index_creation = time.time() 
 
    while stop_event is None or stop_event.is_set() is False:
        async for account in MongoDBAsync.account_data.find({"make_feed" : True}):
            asyncio.create_task(do_feed(account["_id"], stop_event))
            await asyncio.sleep(0.01)

        # Time for new Posts Search Index? - All 120 Minutes, it takes max. some min to create an
        # index so I do not need to measure the exact creation time, just when it is called
        if (last_search_index_creation + 120 * 60) < time.time():
            asyncio.create_task(PostsCategory.create_search_index(waiting_intervall = 100))
            last_search_index_creation = time.time()     

        # DO open_updates
        # Not use open_updates directly because while the BulkWrite is happening
        # It can occur that some elements are added
        if len(open_db_updates) > 0:
            selected = [item for item in open_db_updates]
            open_db_updates = []

            try:
                await MongoDBAsync.account_data.bulk_write(selected, ordered=False)
            except BulkWriteError:
                pass

        # wait some time
        while 1:
            await asyncio.sleep(0.1)
            if len(currently_makings) < 100:
                break

def start(stop_event = None):
    '''Starts the async process'''    
    asyncio.run(run(stop_event=stop_event))

if __name__ == '__main__':
   start()


   