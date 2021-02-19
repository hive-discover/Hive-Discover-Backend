#import asyncio
import os, sys, time
#from threading import Thread
from multiprocessing import Process
sys.path.append(os.getcwd() + "/.")

from account_manager import feed_making, account_analyzer
#from database import MongoDB
#from agents import PostsCategory
#from hive import AccountsManager
#from multi_agents import AccountAnalyzer, AccountFeedMaker

#feed_makings_accounts = []
#account_analyzer_accounts = []

async def manage_posts_index():
    # Make Search Indexes
    PostsCategory.search_index = None
    while 1:
        await PostsCategory.create_search_index()
        # wait a bit
        time.sleep(60 * 5)
        

async def make_feed_container(account : str):
    # Test if locked, else lock it
    await MongoDB.account_table.update_one({"name" : account}, {"$unset" : {"make_feed" : ""}}) 
    if account in feed_makings_accounts:
        return
    feed_makings_accounts.append(account)

    while PostsCategory.search_index is None:
        await asyncio.sleep(1)

    # Do it
    maker = AccountFeedMaker(account, PostsCategory.search_index)
    maker.start()

    # Wait till finish and free account
    while maker.is_alive():
        await asyncio.sleep(1)  
    feed_makings_accounts.remove(account)

async def analyze_account_container(account : str):
    # Test if locked, else lock it
    await MongoDB.account_table.update_one({"name" : account}, {"$unset" : {"analyze" : ""}}) 
    if account in account_analyzer_accounts:
        return
    account_analyzer_accounts.append(account)

    # Do it
    analyzer = AccountAnalyzer(account)
    analyzer.start()

    # Wait till finish and free account
    while analyzer.is_alive():
        await asyncio.sleep(1)  
    account_analyzer_accounts.remove(account)


async def run():
    await MongoDB.account_table.update_one({"name" : "christopher2002"}, {"$set" : {"make_feed" : True}}) 
    while 1:
        if len(account_analyzer_accounts) < 250:
            # Check for analyze_requests
            async for acc in MongoDB.account_table.find({"analyze" : True}):     
                asyncio.create_task(analyze_account_container(acc["name"]))

        if len(feed_makings_accounts) < 250:
            # Check for feed_requests
            async for acc in MongoDB.account_table.find({"make_feed" : True}):
                asyncio.create_task(make_feed_container(acc["name"]))

        time.sleep(2.5)


def start_manager():
    mp_feeds = Process(target=feed_making.start, name="Feed Making Process", daemon=True)
    mp_analyze = Process(target=account_analyzer.start, name="Anylze Accounts Process", daemon=True)
    mp_feeds.start()
    mp_analyze.start()
    
    return
    MongoDB.init_global(post_table = True, account_table = True, banned_table = True)
    Thread(target=manage_posts_index, name="Posts Search Indexer", daemon=True).start()

    async def all():
        await asyncio.wait([run(), manage_posts_index()])

    loop = asyncio.get_event_loop()
    loop.run_until_complete(all())
    loop.close()

if __name__ == '__main__':
   start_manager()

