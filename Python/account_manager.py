from database import MongoDBAsync

from pymongo.errors import BulkWriteError
from pymongo.operations import UpdateOne

from beem import Hive
from beem.account import Account
from beem.exceptions import AccountDoesNotExistsException

import asyncio
import secrets

async def generate_account_ids(amount : int = 1) -> list:
    '''Generate some unused ids'''
    choosed = set([])
    while len(choosed) < amount:
        some_ids = [secrets.randbelow(2000000000) for _ in range(10 * amount * 2)]
        async for used_ids in MongoDBAsync.account_info.find({"_id" : {"$in" : some_ids}}, {"_id" : 1}):
            some_ids.remove(used_ids["_id"])
        
        for _id in some_ids:
            choosed.add(_id)

    return list(choosed)[0:amount]


#   *** Find Accounts ***
async def username_to_id(usernames : list) -> list:
    '''Get _ids of usernames. -1 if it does not exist'''
    # Prepare
    account_ids = [-1 for _ in usernames]

    cursor = MongoDBAsync.account_info.find({"name" : {"$in" : usernames}})

    # Find and Set _ids
    async for account in cursor:
        for index, username in enumerate(usernames):
            if username == account["name"]:
                account_ids[index] = account["_id"]

    return account_ids

async def get_account_data(accounts : list) -> list:
    '''Return a list of account_data documents in the same order. When it does not exist it is None. accounts can be names as str or _id'''
    if len(accounts) == 0:
        return []   

    if isinstance(accounts[0], str):
        # Convert Usernames to _id
        accounts = await username_to_id(accounts)

    cursor = MongoDBAsync.account_data.find({"_id" : {"$in" : accounts}})

    # Set correct data in list
    account_data = [None for _ in accounts]
    async for db_acc in cursor:
        for index, in_acc in enumerate(accounts):
            if in_acc == db_acc["_id"]:
                account_data[index] = db_acc

    return account_data

async def get_account_info(accounts : list) -> list:
    '''Return a list of get_account_info documents in the same order. When it does not exist it is None. accounts can be names as str or _id'''
    if len(accounts) == 0:
        return []
    
    cursor = None 
    if isinstance(accounts[0], str):
        # Usernames
        cursor = MongoDBAsync.account_info.find({"name" : {"$in" : accounts}})
    if isinstance(accounts[0], int):
        # _id
        cursor = MongoDBAsync.account_info.find({"_id" : {"$in" : accounts}})

    account_info = [None for _ in accounts]
    if cursor:
        # Set correct data in list
        async for db_acc in cursor:
            for index, in_acc in enumerate(accounts):
                if in_acc == db_acc["name"] or in_acc == db_acc["_id"]:
                    account_info[index] = db_acc

    return account_info
   


async def update_account_profile(accounts : list, profiles : list) -> None:
    '''Updates an account profile's to a new one. Accounts can be names or _ids. Profiles has to be dicts'''
    if len(accounts) == 0 or len(profiles) == 0 or len(accounts) != len(profiles):
        return []

    # Prepare updates
    updates = [] # No upserts because it will cause to create an ObjectID
    if isinstance(accounts[0], str):
        # accounts are usernames 
        updates = [UpdateOne({"name" : name}, {"$set" : {"profile" : profile}}) for name, profile in zip(accounts, profiles)]
    if isinstance(accounts[0], int):
        # accounts are _id 
        updates = [UpdateOne({"_id" : name}, {"$set" : {"profile" : profile}}) for name, profile in zip(accounts, profiles)]

    # Make updates
    if len(updates) > 0:
        try:
            await MongoDBAsync.account_info.bulk_write(updates, ordered=False)
        except BulkWriteError:
            pass



async def remove_banned(usernames : list, post_ids : list) -> list:
    '''Remove all banned accs'''
    async for banned in MongoDBAsync.banned.find({"name" : {"$in" : usernames}}):
        for index, _ in enumerate(usernames):
            if usernames[index] == banned["name"]:
                post_ids[index] = 0
    return post_ids

async def append_accounts(usernames : list, save_call = True) -> list:
    '''Add all accounts and return there _ids'''
    # Get all _ids of already entered, else they are -1
    account_ids = await username_to_id(usernames)
    account_ids = await remove_banned(usernames, account_ids)
    open_ids = await generate_account_ids(len(usernames))

    # Check whether they exist
    if not save_call:
        for index, acc in enumerate(usernames):
            try:
                acc = Account(acc, instance=Hive(), full=False)
            except AccountDoesNotExistsException:
                account_ids[index] = -1

    # Enter all -1 indexes
    new_accounts = []
    for index, name in enumerate(usernames):
        if account_ids[index] > -1:
            # Already inside, banned or else
            continue
        
        account_ids[index] = open_ids[index]
        new_accounts.append({"_id" : open_ids[index], "name" : name})

    if len(new_accounts) > 0:
        try:
            await MongoDBAsync.account_info.insert_many(new_accounts)
        except BulkWriteError:
            pass
    return account_ids

async def get_more_accounts():
    '''Get similar accounts'''
    import requests, json

    urls = ["https://api.openhive.network", "https://api.hive.blog"]
    new_accs = []
    counter = 0
    async for account_info in MongoDBAsync.account_info.find({}).skip(7000):
        # Prepare URL and payload
        url = urls[0] if (counter % 2) == 0 else urls[1]
        payload = '{"jsonrpc":"2.0", "method":"condenser_api.lookup_accounts", "params":["' + account_info["name"] + '", 100], "id":1}'
        counter += 1
        print("", end=f"\r Current index: {counter}. Len of new_accs: {len(new_accs)}")

        # Make request and format
        res = requests.post(url, data=payload)
        try:
            data = json.loads(res.text)
        except:
            continue

        # Add to new_accs
        if "result" in data and isinstance(data["result"], list):
            [new_accs.append(item) for item in data["result"]]

        # Enough --> Append them
        if len(new_accs) > 2500:
            await append_accounts(new_accs)
            new_accs = []

async def delete_accounts(accounts : list) -> bool:
    '''Delete all data by an account. accounts can be usernames or _ids. Returns if it was succesfull'''
    if len(accounts) == 0:
        return False

    # Make sure to have _ids
    if isinstance(accounts[0], str):
        accounts = await username_to_id(accounts)

    # Delete 
    await asyncio.wait([
        MongoDBAsync.account_info.delete_many({"_id" : {"$in" : accounts}}),
        MongoDBAsync.account_data.delete_many({"_id" : {"$in" : accounts}}),
        MongoDBAsync.post_data.update_many({}, {"$pull" : {"votes" : {"$in" : accounts}}})
    ])
    return True
    
async def ban_accounts(accounts : list) -> bool:
    '''Ban accounts. Accounts can be usernames or _ids. Return if it was succesfull'''
    if len(accounts) == 0:
        return False
    usernames, ids = [], []

    # Make sure to have both
    if isinstance(accounts[0], str):
        usernames = accounts
        ids = await username_to_id(accounts)

    elif isinstance(accounts[0], int):
        ids = accounts
        usernames = [acc["name"] async for acc in MongoDBAsync.account_info.find({"_id" : {"$in" : accounts}})]
    
    await delete_accounts(ids)
    await MongoDBAsync.banned.insert_many([{"name" : x} for x in usernames])
    return True

if __name__ == '__main__':
    async def do():
        MongoDBAsync.init_global(post_table=True, banned_table=True, account_table=True)
        print(await get_more_accounts())
    asyncio.run(do())
    

