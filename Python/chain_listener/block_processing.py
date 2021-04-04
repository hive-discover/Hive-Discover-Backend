import json
import asyncio
import sys, os
sys.path.append(os.getcwd() + "/.") 

'''
from pymongo import UpdateMany
from pymongo.errors import BulkWriteError
from database import MongoDBAsync
from hive import PostsManager


async def account_updatessss(actions : list) -> None:
     
    tasks_running = []
    bulk_updates = []
    for action in actions:
        username, metadata = action["account"], action["json_metadata"]

        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}

        if "profile" in metadata:
            metadata = metadata["profile"]

        # Retrieve all possible data
        profile = {}        
        if "name" in metadata:
            profile["name"] = metadata["name"]
        if "about" in metadata:
            profile["about"] = metadata["about"]
        if "location" in metadata:
            profile["location"] = metadata["location"]

        # Enter. Also if nothing is in profile because maybe user deleted some entries
        bulk_updates.append(UpdateMany({"name" : username}, {"$set" : {"profile" : profile}}))
        #tasks_running.append(MongoDBAsync.account_table.update_one({"name" : username}, {"$set" : {"profile" : profile}}))

    if len(bulk_updates) > 0:
        try:
            await MongoDBAsync.account_table.bulk_write(bulk_updates, ordered=False)
        except BulkWriteError:
            pass

    if len(tasks_running) > 0:
        await asyncio.wait(tasks_running)

async def account_votes(actions : list) -> None:
   
    if len(actions) == 0:
        return

    # Prepare everything
    voters = [x["voter"] for x in actions]
    authors = [x["author"] for x in actions]
    permlinks = [x["permlink"] for x in actions]
    posts = [post async for post in MongoDBAsync.post_table.find({"author" : {"$in" : authors}, "permlink" : {"$in" : permlinks}})]

    # Get all accounts from DB. When loading is False, it is analyzed but not currently 
    tasks_running = []
    bulk_updates = []
    async for acc in MongoDBAsync.account_table.find({"name" : {"$in" : voters}, "loading" : False}):
        vote_index = -1
        for index, voter in enumerate(voters):
            if voter == acc["name"]:
                # Found correct vote and his index
                vote_index = index
                break

        if vote_index >= 0:
            # Find post_id and push it
            voter, author, permlink = voters[vote_index], authors[vote_index], permlinks[vote_index]
            for post in posts:
                if post["author"] == author and post["permlink"] == permlink:
                    bulk_updates.append(UpdateMany({"name" : voter}, {"$addToSet" : {"votes" : post["post_id"] }}))
                    #tasks_running.append(MongoDBAsync.account_table.update_one({"name" : voter}, {"$push" : {"votes" : post["post_id"] }}))
                    break
    
    if len(bulk_updates) > 0:
        try:
            await MongoDBAsync.account_table.bulk_write(bulk_updates, ordered=False)
        except BulkWriteError:
            pass

    if len(tasks_running) > 0:
        await asyncio.wait(tasks_running)

async def account_posts(posts, timestamp) -> None:
   
    if len(posts) == 0:
        return

    author_list = [post["author"] for post in posts]
    post_ids = await PostsManager.append_async_posts(
                    posts, timestamp)

    # Enter Posts in Post-List by an analyzed account
    # When loading is False, no one is analyzing him and it was analyzed so it's perfect
    tasks_running = []
    async for account in MongoDBAsync.account_table.find({"name" : {"$in" : author_list}, "loading" : False}):
        # Find correct post, get index and push post_id
        for index, post in enumerate(posts):
            if post["author"] == account["name"] and post_ids[index] > 0:
                t = MongoDBAsync.account_table.update_many({"name" : account["name"]}, {"$push" : {"posts" : post_ids[index] }})
                tasks_running.append(t)

    if len(tasks_running) > 0:
        await asyncio.wait(tasks_running)

async def insert_accounts(accounts : list) -> None:
    
    if len(accounts) == 0:
        return

    # Two async functions to do it concurrently (One is waiting, the other is removing or does account_votes or ...) 
    # --> Faster
    async def remove_listed_accs() -> int:

        async for listed_acc in MongoDBAsync.account_table.find({"name" : {"$in" : accounts}}):
            accounts.remove(listed_acc["name"])
        return 0

    async def remove_banned_accs() -> int:
        async for banned_acc in MongoDBAsync.banned_table.find({"name" : {"$in" : accounts}}):
            accounts.remove(banned_acc["name"])
        return 0

    # Remove them
    await asyncio.gather(remove_banned_accs(), remove_listed_accs())

    if len(accounts) == 0:
        return

    # insert all other
    try:
        await MongoDBAsync.account_table.insert_many([{"name" : acc} for acc in accounts])
    except BulkWriteError:
        pass
'''

from account_manager import append_accounts, update_account_profile
from posts_manager import append_posts, add_votes_to_posts


async def account_updates(actions : list):
    # Prepare Data
    usernames = [x["account"] for x in actions]
    metadata = [x["json_metadata"] for x in actions]

    for index, x in enumerate(metadata):
        try:
            metadata[index] = json.loads(x)
        except json.JSONDecodeError:
            metadata[index] = {}

    # Make Profiles
    profiles = []
    for data in metadata:
        if "profile" in data:
            data = data["profile"]

        # Retrieve all possible data
        profile = {}        
        if "name" in data:
            profile["name"] = data["name"]
        if "about" in data:
            profile["about"] = data["about"]
        if "location" in data:
            profile["location"] = data["location"]

        profiles.append(profile)

    await update_account_profile(usernames, profiles)

async def account_votes(actions : list):
    voters = [x["voter"] for x in actions]
    authors = [x["author"] for x in actions]
    permlinks = [x["permlink"] for x in actions]

    await add_votes_to_posts(voters, (authors, permlinks))

def filter_transactions(operations) -> tuple:
    '''Filter for interesting operations and return them like: (post_ops, vote_ops, acc_ops, accounts) <-- all lists'''
    post_ops, vote_ops, acc_update_ops, accounts = [], [], [], []
    for op in operations:
        action = op['value']

        if op['type'] == 'comment_operation' and action['parent_author'] == '':
            # found Post, no comment
            post_ops.append(action)
            accounts.append(action["author"])

        elif op['type'] == 'vote_operation':
            # found Vote
            vote_ops.append(action)
            accounts.append(action["voter"])
            accounts.append(action["author"])

        elif op['type'] == 'account_update_operation':
            # found Account Update
            acc_update_ops.append(action)
            accounts.append(action["account"])
    
    return (post_ops, vote_ops, acc_update_ops, accounts)

async def process_block(block):
    '''Processes one block, filter and do updates'''
    post_ops, vote_ops, acc_update_ops, accounts = filter_transactions(block.operations)
    await asyncio.wait([ append_posts(post_ops),
                         append_accounts(accounts),
                         account_votes(vote_ops),
                         account_updates(acc_update_ops) ])

    #await asyncio.wait([
    #            account_posts(post_ops, block["timestamp"]),
    #            account_votes(vote_ops),
    #            account_updates(acc_update_ops),
     #           insert_accounts(accounts)
     #               ])
