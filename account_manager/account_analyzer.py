import asyncio
from datetime import datetime
import os, sys
sys.path.append(os.getcwd() + "/.")

from database import MongoDBAsync
from hive import PostsManager

import numpy as np
from beem.account import Account
from beem.exceptions import AccountDoesNotExistsException

currently_analyzings = [] # account_names

def get_account_operations(acc : Account) -> tuple:
    '''Get all hive operations with vote and comment. Returns a tuple of (operations, amount)'''
    operations = acc.history_reverse(only_ops=['comment', 'vote'])
    amount = np.sum(1 for _ in operations)
    operations = acc.history_reverse(only_ops=['comment', 'vote'])
    return (operations, amount)

def get_hive_account(account : str) -> Account:
    '''Get a hive account. If it not exists, it wil return None'''
    try:
        return Account(account)
    except AccountDoesNotExistsException:
        return None

async def process_operations(account : str, operations, amount : int) -> None:
    '''Iterater through all operations and enter important things into DB'''
    for index, operation in enumerate(operations):
        await MongoDBAsync.account_table.update_one({"name" : account}, {"$set" : {"loading" : { "current" : (index + 1), "max" : amount} }})
            
        # Test if Vote
        if operation["type"] == "vote":
            if operation["voter"] == account and operation["voter"] != operation["author"]:
                # Vote from him to a foreign post
                post_ids = await PostsManager.append_async_posts_gentle(authors=[operation['author']], permlinks=[operation['permlink']])
                if len(post_ids) > 0 and post_ids[0] >= 0:
                    # Append to list
                    await MongoDBAsync.account_table.update_one({"name" : account}, {"$push" : {"votes" : post_ids[0] }})

        
        # Test if Post
        if operation["type"] == "comment":
            if operation["author"] == account:
                # He wrote the Post and is no comment
                if operation["parent_author"] == '':
                    post_ids = await PostsManager.append_async_posts_gentle(authors=[operation['author']], permlinks=[operation['permlink']])
                    if len(post_ids) > 0 and post_ids[0] >= 0:
                        # Append to list
                        await MongoDBAsync.account_table.update_one({"name" : account}, {"$push" : {"posts" : post_ids[0] }})

async def do_analyze(account : str):
    '''Analyzes an account'''
    await MongoDBAsync.account_table.update_one({"name" : account}, {"$unset" : {"analyze" : ""}}) 
    # Lock Account
    if account in currently_analyzings:
        return
    currently_analyzings.append(account)    

    # Check if too much is running
    while len(currently_analyzings) > 200:
        await asyncio.sleep(0.5)

    # Get account, check if banned, get operations and Prepare Account
    hive_acc = get_hive_account(account)
    if await MongoDBAsync.banned_table.find_one({"name" : account}) or hive_acc is None:
        await MongoDBAsync.account_table.delete_one({"name" : account}) 
        return    
    operations, amount = get_account_operations(hive_acc)

    await MongoDBAsync.account_table.update_one({"name" : account},
                 {"$set" : {"posts" : [], "votes" : [], "make_feed" : True,
                    "loading" : { "current" : 0, "max" : amount}}})

    # Do it and wait for completing
    await process_operations(account, operations, amount)
    await MongoDBAsync.account_table.update_one({"name" : account}, 
                        {"$set" : {"last_analyze" : datetime.utcnow(),
                                     "loading" : False}})

    # Free Account
    currently_analyzings.remove(account) 

async def run(stop_event = None):
    '''Endless Loop: Runner for this Process'''
    MongoDBAsync.init_global(post_table = True, account_table = True, banned_table = True)
    
    while stop_event is None or stop_event.is_set() is False:
        async for account in MongoDBAsync.account_table.find({"analyze" : True}):
            asyncio.create_task(do_analyze(account["name"]))

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
