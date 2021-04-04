import asyncio
from datetime import datetime, timedelta
import os, sys
from typing import Generator

from pymongo.operations import UpdateOne
sys.path.append(os.getcwd() + "/.")

from pymongo import UpdateMany
from pymongo.errors import BulkWriteError
from database import MongoDBAsync

from beem.account import Account
from beem.exceptions import AccountDoesNotExistsException

currently_analyzings = [] # account_names
open_updates_accounts, open_updates_posts = [], []

def get_account_operations(acc : Account) -> Generator:
    '''Get all hive operations with vote and comment'''
    stop = datetime.utcnow() - timedelta(days=100)
    operations = acc.history_reverse(only_ops=['vote'], stop=stop)#'comment', 
    return operations

def get_hive_account(account : str) -> Account:
    '''Get a hive account. If it not exists, it wil return None'''
    try:
        return Account(account)
    except AccountDoesNotExistsException:
        return None   

async def process_operations(account_id : int, account_name : str, operations) -> None:
    '''Iterater through all operations and enter important things into DB'''
    global open_updates_posts 
    authors, permlinks = [], []

    # Filter for all authors, permlinks
    for operation in operations:          
        # Test if Vote (Normally it should be)
        if operation["type"] == "vote":
            if operation["voter"] == account_name and operation["voter"] != operation["author"]:
                # Vote from him to a foreign post 
                authors.append(operation["author"])
                permlinks.append(operation["permlink"])
                await asyncio.sleep(0.125)

    # Get all post_ids
    post_ids = [post["_id"] async for post in MongoDBAsync.post_info.find({
        "author" : {"$in" : authors},
        "permlink" : {"$in" : permlinks}
        })]
    
    # Add the votes
    open_updates_posts += [UpdateMany({"_id" : {"$in" : post_ids}}, {"$addToSet" : {"votes" : account_id}})]
                           
async def do_analyze(account_id : int):
    '''Analyzes an account'''
    global open_updates_accounts
    open_updates_accounts.append(UpdateMany({"_id" : account_id}, {"$unset" : {"analyze" : ""}}))

    # Lock Account
    if account_id in currently_analyzings:
        return
    currently_analyzings.append(account_id)    

    # Check if too much is running
    while len(currently_analyzings) > 200:
        await asyncio.sleep(5)

    # Get first account_info, then hive account
    account_info = await MongoDBAsync.account_info.find_one({"_id" : account_id})
    if not account_id:
        # Something weird
        currently_analyzings.remove(account_id) 
        return

    hive_acc = get_hive_account(account_info["name"])  
    open_updates_accounts.append(UpdateMany({"_id" : account_id}, 
                                   {"$set" : {"make_feed" : True, "loading" : True}}))

    # Do it and wait for completing and let feed making (again that's why delete feed)
    operations = get_account_operations(hive_acc)
    await process_operations(account_id, account_info["name"], operations)

    # Finished
    open_updates_accounts.append(UpdateMany({"_id" : account_id}, 
                        {"$set" :  { "last_analyze" : datetime.utcnow(),
                         "make_feed" : True, "feed" : [],
                         "loading" : False}}))

    # Free Account
    currently_analyzings.remove(account_id) 

 
async def run(stop_event = None):
    '''Endless Loop: Runner for this Process'''
    global open_updates_accounts, open_updates_posts
    MongoDBAsync.init_global(post_table = True, account_table = True, banned_table = True)
    
    while stop_event is None or stop_event.is_set() is False:
        # Check for Analyze requests
        async for account in MongoDBAsync.account_data.find({"analyze" : True}):
            asyncio.create_task(do_analyze(account["_id"]))
            await asyncio.sleep(0.1)

        # DO open_updates_accounts
        if len(open_updates_accounts) > 0:
            selected = open_updates_accounts[:]
            open_updates_accounts = []

            try:
                await MongoDBAsync.account_data.bulk_write(selected, ordered=False)
            except BulkWriteError:
                pass

        # DO open_updates_posts
        if len(open_updates_posts) > 0:
            selected = open_updates_posts[:]
            open_updates_posts = []

            try:
                await MongoDBAsync.post_data.bulk_write(selected, ordered=False)
            except BulkWriteError:
                pass
            

        # wait some time
        while 1:
            await asyncio.sleep(0.25)
            if len(currently_analyzings) < 100:
                break

def start(stop_event = None):
    '''Starts the async process'''    
    asyncio.run(run(stop_event=stop_event))

if __name__ == '__main__':
   start()
