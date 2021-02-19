import asyncio
import multiprocessing as mp
from threading import Thread
import secrets
import os, sys, time
sys.path.append(os.getcwd() + "/.")

from database import MongoDBAsync
from agents import PostsCategory
from hive import AccountsManager
from config import *

currently_makings = [] # account_names
 
async def do_feed(account : str, stop_event, delete_old = False):
    await MongoDBAsync.account_table.update_one({"name" : account}, {"$unset" : {"make_feed" : ""}})
    if account in currently_makings:
        return
    currently_makings.append(account)

    acc_langs = []
    last_posts_count, last_votes_count = 0, 0
    counter = 0
    while stop_event is None or not stop_event.is_set():
        acc = await MongoDBAsync.account_table.find_one({"name" : account})
        if not acc:
            # no account -> something went wrong
            break

        if ("posts" not in acc or "votes" not in acc) or (len(acc["posts"]) == 0 and len(acc["votes"]) == 0):
            # Put analyze request into DB and wait a bit
            await MongoDBAsync.account_table.update_one({"name" : account}, {"$set" : {"analyze" : True}})
            await asyncio.sleep(1)
            continue
        
        # Get Lang from Account (Only when it is empty or new votes/posts are available) and make it as a 
        # simple List. From [{...}, {...}] to ["...", "..."]
        if len(acc_langs) == 0 or last_posts_count != len(acc["posts"]) or last_votes_count != len(acc["votes"]):
            _, acc_langs = await AccountsManager.get_account_cats_and_lang(acc=acc)
            acc_langs = [item["label"] for item in acc_langs]

        acc_posts, acc_votes = acc["posts"], acc["votes"]  
        last_posts_count, last_votes_count = len(acc_posts), len(acc_votes)
        if not "feed" in acc:
            # Setup, only local
            acc["feed"] = []

        feed_list = acc["feed"]
        if len(feed_list) >= ACCOUNT_MIN_FEED_LEN and delete_old is False:
            # Succes, feed_list is full
            break

        # Get Post Ids (similar)
        similar_posts = []
        if len(acc_posts) > 0:
            # Get similar posts like his own
            own_post_ids = [secrets.choice(acc_posts) for _ in range(0, secrets.randbelow(len(acc_posts)))]
            search_results = await PostsCategory.search(own_post_ids, k=(10 + counter * 2))
            similar_posts += search_results["results"]
            
        if len(acc_votes) > 0:
            # Get similar posts like he voted
            voted_post_ids = [secrets.choice(acc_votes) for _ in range(0, secrets.randbelow(len(acc_votes)))]
            search_results = await PostsCategory.search(voted_post_ids, k=(5 + counter * 2))
            similar_posts += search_results["results"]

        counter += 1

        # Extrace Similar Post IDs
        open_ids = []
        for item in similar_posts:
            # Enter all in open_ids
            open_ids += [result["post_id"] for result in item["results"]]

        # Check if not liked or not own posts
        for _id in open_ids:
            if _id in acc_votes:
                open_ids.remove(_id)
            if _id in acc_posts:
                open_ids.remove(_id)

        # Choose randoms and heck langs from the posts: Query for id and lang (it will only return matches)
        amount = min(len(open_ids), ACCOUNT_MAX_FEED_LEN)
        open_ids = [secrets.choice(open_ids) for _ in range(amount)]
        open_ids = [post["post_id"] async for post in MongoDBAsync.post_table.find({"post_id" : {"$in" : open_ids}, "lang" : {"$elemMatch" : {"lang" : {"$in" : acc_langs}}}})]

        # Enter them
        if len(open_ids) > 0:
            if delete_old:
                await MongoDBAsync.account_table.update_one({"name" : account}, {"$set" : {"feed" : []}})
                delete_old = False            
            await MongoDBAsync.account_table.update_one({"name" : account}, {"$addToSet" : {"feed" : {"$each" : open_ids}}})

    currently_makings.remove(account)
 
async def run(stop_event = None):
    '''Endless Loop: Runner for this Process'''
    MongoDBAsync.init_global(post_table = True, account_table = True, banned_table = True)
    await PostsCategory.create_search_index()
    last_search_index_creation = time.time()
    tasks = []

    while stop_event is None or stop_event.is_set() is False:
        async for account in MongoDBAsync.account_table.find({"make_feed" : True}):
            asyncio.create_task(do_feed(account["name"], stop_event))

        # Time for new Posts Search Index? - All 10 Minutes, it takes max. 60sec to create an
        # index so I do not need to measure the exact creation time, just when it is called
        if (last_search_index_creation + 10 * 60) > time.time():
            #asyncio.create_task(PostsCategory.create_search_index())
            last_search_index_creation = time.time()     

        # wait some time
        while 1:
            await asyncio.sleep(0.5)
            if len(currently_makings) < 100:
                break

def start(stop_event = None):
    '''Starts the async process'''    
    asyncio.run(run(stop_event=stop_event))

if __name__ == '__main__':
   start()