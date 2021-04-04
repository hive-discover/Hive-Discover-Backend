from beem import Hive 
from beem.blockchain import Blockchain
from beem.account import Account
from beem.exceptions import AccountDoesNotExistsException

import asyncio
import time
import secrets
import sys, os
sys.path.append(os.getcwd() + "/.")

from config import *
from database import MongoDBAsync
from helper import helper
from chain_listener.block_processing import process_block


async def manage_account_data(instance = None) -> None:
    '''Get account data like location and description for accounts which does not have them'''
    if not instance:
        instance = Hive()

    last_hive_call = time.time()
    while 1:
        # Process all accounts, which does not have the "profile" field        
        async for account in MongoDBAsync.account_info.find({"profile" : {"$exists" : False}}):
            # Wait at least 0.075 seconds between every hive call
            diff = (time.time() - last_hive_call)
            if diff < 0.075:
                await asyncio.sleep(0.075 - diff)

            try:
                hive_acc = Account(account["name"], blockchain_instance=instance)
                last_hive_call = time.time()
            except AccountDoesNotExistsException:
                await MongoDBAsync.account_table.delete_many({"name" : account["name"]})
                continue

            # Retrieve all profile data and update acc document
            
            profile = {}     

            try:
                metadata = hive_acc.profile
                if "name" in metadata:
                    profile["name"] = metadata["name"]
                if "about" in metadata:
                    profile["about"] = metadata["about"]
                if "location" in metadata:
                    profile["location"] = metadata["location"]
            except:
                pass
            await MongoDBAsync.account_info.update_one({"name" : account["name"]}, {"$set" : {"profile" : profile}})

        # wait
        await asyncio.sleep(10)

async def get_init_current_num(chain : Blockchain) -> int:
    '''Retrieves the current_bloc_num from DB or creates a new one'''
    state = await MongoDBAsync.stats_table.find_one({"tag" : "CURRENT_BLOCK_NUM"})
    if not state:
        return chain.get_current_block_num() - 2500
    
    # Last current_block_num is inside --> then why not use it
    return state["current_num"]
        
async def manage_block_data(instance = None):
    '''Get all Blocks and process each one'''
    if not instance:
        instance = Hive()

    chain = Blockchain(blockchain_instance=instance)
    current_num = await get_init_current_num(chain)

    while 1:
        start_time = time.time()

        if (current_num + 5) < chain.get_current_block_num():
            # Block(s) available
            # Wait here to get afterwards really all blocks and not wait because then 
            # a new block is (maybe) available and the else statement never runs   
            amount = chain.get_current_block_num() - current_num
            if amount > 500: 
                # max 500
                amount = 500

            # Get Blocks and operations
            tasks = []
            counter = 0
            for block in chain.blocks(start=current_num, stop=(current_num + amount), max_batch_size=50):  
                if (counter % 33) == 0:
                    await asyncio.sleep(0.05) 
                counter += 1
                tasks.append(process_block(block))

            if len(tasks) > 0:
                await asyncio.wait(tasks)

            # Finished
            time_took = time.time() - start_time
            blocks_per_second = amount / time_took
            current_num += (amount + 1)   
            print(blocks_per_second)

            # Enter in DB
            await MongoDBAsync.stats_table.update_one({"tag" : "CURRENT_BLOCK_NUM"}, {"$set" : {"current_num" : current_num}}, upsert=True)
        else:
            print("waiting")
            await asyncio.sleep(30)

        if secrets.randbelow(20) <= 5:
            chain = Blockchain(blockchain_instance=instance)
            print("New Blockchain object")

 
def start_listener():
    '''Container for this Sub Application'''
    MongoDBAsync.init_global(post_table=True, account_table=True, banned_table=True, stats_table=True)
    helper.init()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.gather(
        manage_block_data(instance=Hive(node="https://api.openhive.network")),
        manage_account_data(instance=Hive(node="https://hive-api.arcange.eu"))
        ))
    loop.close()


if __name__ == '__main__':
   start_listener() 
