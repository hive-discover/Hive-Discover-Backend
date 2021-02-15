import pymongo
from fastapi import APIRouter, Depends

import time
import sys, os
sys.path.append(os.getcwd() + "/.")

from config import *
from database import MongoDB
from agents import AccountSearch
from api.models import *
from api.stats import add_statistic

router = APIRouter()
 
@router.post("/posts", response_model=PostsResponse)
async def search_posts(p_search : PostsSearch, _ = Depends(add_statistic)):
    '''Searches for posts in MongoDB'''
    start_time = time.time()

    # Create find_query
    find_query = {'$text': {'$search': p_search.query}}
    if len(p_search.lang):
        find_query["lang"] = {"$elemMatch" : {"lang" : {"$in" : p_search.lang}}}

    # Search in DB     
    cursor = MongoDB.post_table.find(find_query, {'score': {'$meta': 'textScore'}}).limit(p_search.max)#.sort()
    cursor.sort([("timestamp", pymongo.DESCENDING), ('score', {'$meta': 'textScore'})])

    # Format posts
    posts = []
    async for post in cursor:
        item = {"author" : post["author"], "permlink" : post["permlink"]}     
        if "lang" in post and not post["lang"] is None:
            item["lang"] = [item["lang"] for item in post["lang"]]
        posts.append(item)

    return {"status" : "ok", "posts" : posts, "amount" : len(posts), "total" : int(await MongoDB.post_table.count_documents({})), "seconds" : time.time() - start_time}

@router.post("/accounts", response_model=AccountSearchResponse)
async def search_accounts(acc_search : AccountsSearch, _ = Depends(add_statistic)):
    '''Searches for Accounts via the Search-Index or MongoDB'''
    if acc_search.mode == AccountSearchMode.username:
        search_results = AccountSearch.search_by_username(acc_search.query, max=acc_search.max)
    else:
        search_results = AccountSearch.search_by_bio(acc_search.query, max=acc_search.max)
    
    accounts = search_results["results"]
    return {"status" : "ok", "accounts" : accounts, "amount" : len(accounts), "total" : search_results["records"], "seconds" : search_results["seconds"]}


