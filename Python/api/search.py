from typing import Iterable
from fastapi import APIRouter, Depends

import time
import asyncio
import sys, os

from numpy.lib.function_base import iterable
sys.path.append(os.getcwd() + "/.")

from config import *
from database import MongoDBAsync
from agents import AccountSearch
from api.models import *
from api.stats import add_statistic

router = APIRouter()
  
@router.post("/posts", response_model=PostsResponse)
async def search_posts(p_search : PostsSearch, _ = Depends(add_statistic)):
    '''Searches for posts in MongoDB'''
    start_time = time.time()  

    # Search in post_text. Limit max to 10k ids     
    ids = []
    cursor = MongoDBAsync.post_text.find({'$text': {'$search': p_search.query}},
                                         {'score': {'$meta': 'textScore'}, "_id" : 1, "tag_str" : 1})
    cursor.sort([('score', {'$meta': 'textScore'}), ("timestamp", -1)])
    

    if len(p_search.lang) == 0:
        cursor.limit(p_search.max)
    else:
        # If langs are specified it needs a buffer
        cursor.limit(1000)

    posts = [(post["_id"], post["tag_str"]) async for post in cursor]
    ids, tags = [p[0] for p in posts], [p[1].split(' ') for p in posts]
    posts = [{} for _ in posts]
    total_posts = [0]

    async def set_authorperm():
        '''Set authorperms from search results'''
        async for post_info in MongoDBAsync.post_info.find({"_id" : {"$in" : ids}}):
            for index, post_id in enumerate(ids):
                # Find correct place. If posts[index] is None, a lang is selected and the 
                # post does not match it 
                if posts[index] is not None and post_id == post_info["_id"]:               
                    posts[index]["author"] = post_info["author"]
                    posts[index]["permlink"] = post_info["permlink"]
                    posts[index]["tags"] = tags[index]
    
    async def set_langs():
        '''Set langs and if a lang is seleced it will filter out'''
        async for post_data in MongoDBAsync.post_data.find({"_id" : {"$in" : ids}}):
            for index, post_id in enumerate(ids):
                # Find correct place
                if posts[index] is not None and post_id == post_data["_id"]:  
                    if not post_data["lang"]:
                        # Was not lang-detected --> set post to None
                        posts[index] = None
                        continue
                    
                    # Reshape lang array and set it
                    post_lang = [item["lang"] for item in post_data["lang"]]             
                    posts[index]["lang"] = post_lang

                    # Check if a lang is specified
                    if len(p_search.lang) > 0:
                        inside = False
                        for selected_lang in p_search.lang:
                            # Check if post_lang matches
                            if selected_lang in post_lang:
                                inside = True
                        
                        if not inside:
                            # Remove --> None setting
                            posts[index] = None

    async def set_total():
        total_posts[0] = await MongoDBAsync.post_text.count_documents({})

    await asyncio.wait([set_authorperm(), set_langs(), set_total()]) 

    # Remove Nones and empty dicts and slice maybe
    posts = [p for p in posts if p and len(p) >= 2]
    if len(posts) > p_search.max:
        posts = posts[:p_search.max]

    return {"status" : "ok", "posts" : posts, "amount" : len(posts), "total" : total_posts[0], "seconds" : time.time() - start_time}

@router.post("/accounts", response_model=AccountSearchResponse)
async def search_accounts(acc_search : AccountsSearch, _ = Depends(add_statistic)):
    '''Searches for Accounts via the Search-Index or MongoDB'''
    search_results = AccountSearch.search_by_bio(acc_search.query, max=acc_search.max)   
    accounts = search_results["results"]
    return {"status" : "ok", "accounts" : accounts, "amount" : len(accounts), "total" : search_results["records"], "seconds" : search_results["seconds"]}


