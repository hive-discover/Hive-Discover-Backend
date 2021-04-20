from datetime import datetime, timedelta
import random, operator
from functools import reduce
import asyncio
from multiprocessing import Process, Queue

import nmslib
import numpy as np
from config import *
from database import MongoDBAsync

search_index = None
last_index_build = None
index_building = False
INDEX_FILENAME = "search_index.bin"

def index_builder():
    async def worker():
        MongoDBAsync.init_global(post_table=True)
        data = None
        current_search_index = nmslib.init(method='hnsw', space='cosinesimil')
        min_date = datetime.utcnow() - timedelta(days=10)

        async for post in MongoDBAsync.post_data.find({"timestamp" : {"$gte" : min_date}, "categories" : {"$size" : len(CATEGORIES)}}, {"_id" : 1, "categories" : 1}):
            # Categories exists and it post from the last 10 days
            data = np.vstack([post["categories"]])
            current_search_index.addDataPointBatch(data, ids=[int(post["_id"])])     
        
        # Build and save it
        current_search_index.createIndex({'post': 2}, print_progress=False)
        current_search_index.saveIndex(INDEX_FILENAME, save_data=True)
    
    asyncio.run(worker())

async def create_search_index():
    '''Creates the search index firstly as a copy in another process, then set it globally'''
    global search_index, index_building, last_index_build
    if index_building:
        return
    index_building = True

    # Start Process and wait
    worekr_process = Process(target=index_builder, name="Test worker")
    worekr_process.start()
    while worekr_process.is_alive():
        await asyncio.sleep(1)
    worekr_process.join()

    # Load it and set
    current_search_index = nmslib.init(method='hnsw', space='cosinesimil')
    current_search_index.loadIndex(INDEX_FILENAME, load_data=True)
    search_index = current_search_index
    last_index_build, index_building = datetime.utcnow(), False

def check_last_index():
    global last_index_build
    if (last_index_build + timedelta(minutes=1)) < datetime.utcnow():
        # time to build index
        loop = asyncio.get_event_loop()
        loop.create_task(create_search_index())

def similar_by_category(query_categories : list, k = 25) -> list:
    '''Searches for similar posts by the categories. Returns a list of similar posts. Shape: [len(query) X k]'''
    global search_index
    check_last_index()
    if not search_index:
        # Is not inited --> return empties
        return [[] for _ in query_categories]

    for index, current_cats in enumerate(query_categories):
        if not isinstance(current_cats, list) or len(current_cats) != len(CATEGORIES):
            # Something weird --> just set it to an empty list
            query_categories[index] = []
            continue

        # Find similar posts and set it into input list
        ids, distances = search_index.knnQuery(np.array(current_cats), k=k)
        query_categories[index] = [int(i) for (i, _) in sorted(zip(ids, distances), key=lambda x: x[1])]

    return query_categories
    
async def similar_by_id(query_ids : list, k = 25):
    '''Searches for similar posts like the id'''
    # Replace ids with categories
    async for post in MongoDBAsync.post_data.find({"_id" : {"$in" : query_ids}, "categories" : {"$size" : len(CATEGORIES)}}, {"_id" : 1, "categories" : 1}):
        for index, q_id in enumerate(query_ids):
            if q_id == post["_id"]:
                query_ids[index] = post["categories"]

    # Get similars. If no post is found / not categorized the ID stays and it get's replaced by an empty list
    # because an integer does not have the len of CATEGORIES
    return similar_by_category(query_ids)

async def get_account_activities(account_id : int = -1, account_name : str = ""):
    if account_id == -1 and len(account_name) < 2:
        return set([]), set([])

    if account_id == -1:
        account_id = (await MongoDBAsync.account_info.find_one({"name" : account_name}))["_id"]
    if account_name == "":
        account_name = (await MongoDBAsync.account_info.find_one({"_id" : account_id}))["name"]

    # Fetch data
    votes, own_posts = {post["_id"] async for post in MongoDBAsync.post_data.find({"votes" : account_id})}, {post["_id"] async for post in MongoDBAsync.post_info.find({"author" : account_name})}
    return (votes, own_posts)

async def get_lang_for_account(votes, own_posts):
    langs = [] # [lang, score (total)]

    async for post in MongoDBAsync.post_data.find({"_id" : {"$in" : list(set().union(*([votes, own_posts])))}, "lang" : {"$exists" : True}}):
        post_langs = post["lang"]

        if post["_id"] in own_posts:
            # His own post --> counts double
            post_langs += post_langs
        
        for lang_obj in post_langs:
            p_lang, p_score = lang_obj["lang"], lang_obj["x"]

            for index, (lang, score) in enumerate(langs):
                if p_lang == lang:
                    # Inside
                    langs[index] = (lang, score + p_score)
                    break
            else:
                # Not inside
                langs.append((p_lang, p_score))

    # Calc percentages and return all over 20%
    total = np.sum([score for _, score in langs])
    langs = [(label, (score/total)) for label, score in langs]
    return [label for label, score in langs if score >= 0.2]



#   *** Make Feeds ***
async def create_normal_feed(account_id : int = -1, account_name : str = "", amount : int = 25) -> list:
    '''Create a Feed for an Account. Returns a list of posts'''
    votes, own_posts = await get_account_activities(account_id, account_name)
    if len(votes) == 0 and len(own_posts) == 0:
        # Unfeedable
        return []

    acc_langs = []
    acc_langs_task = get_lang_for_account(votes, own_posts)

    # Find posts. Max. iterations is 5k
    posts = set([]) # set of post_id to remove duplicates
    for index in range(5000):
        # Get random ids (Max 10 from both)
        query_ids = []
        if len(votes) > 0:
            query_ids += random.sample(votes, min(len(votes), 10))
        if len(own_posts) > 0:
            query_ids += random.sample(own_posts, min(len(own_posts), 10))

        # Get similar ids, flatt the list and insert some
        similarity_ids = await similar_by_id(query_ids, k=(5 + index))
        similarity_ids = reduce(operator.concat, similarity_ids)

        # Remove non spocken langs
        if len(acc_langs) == 0: # wait for task to finish
            acc_langs = await acc_langs_task

        async for post in MongoDBAsync.post_data.find({"_id" : {"$in" : similarity_ids}, "lang" : {"$elemMatch" : {"lang" : {"$in" : acc_langs}}}}, {"_id" : 1}):
            similarity_ids.remove(post["_id"])

        posts.update(similarity_ids)

        # enough posts 
        # ==> a set is always shuffled and now just slice it correctly
        if len(posts) >= amount:
            posts = list(posts)[:amount]
            break
    return posts

async def sort_ids_personalized(account_name : str, query_ids : list):
    posts = [] # (id, category)
    account_index = nmslib.init(method='hnsw', space='cosinesimil')

    # Get data in Parralell
    async def get_categories_from_accounts():
        votes, own_posts = await get_account_activities(account_name=account_name)
        async for post in MongoDBAsync.post_data.find({"_id" : {"$in" : list(set().union(*([votes, own_posts])))}, "categories" : {"$size" : len(CATEGORIES)}}, {"_id" : 1, "categories" : 1}):
            data = np.vstack([post["categories"]])
            account_index.addDataPointBatch(data, ids=[int(post["_id"])]) 
        account_index.createIndex({'post': 2}, print_progress=False)

    async def get_categories_from_query_ids():
        async for post in MongoDBAsync.post_data.find({"_id" : {"$in" : query_ids}, "categories" : {"$size" : len(CATEGORIES)}}, {"_id" : 1, "categories" : 1}):
            posts.append((post["_id"], np.array(post["categories"])))       
    
    await asyncio.wait([get_categories_from_accounts(), get_categories_from_query_ids()])

    if not account_index:
        # Posts and Votes are not available --> just return all ids
        return query_ids

    # Calculate total deviations
    # In Posts the category is set to the total deviation
    # K is not the total amount of activites to not overload everything
    for index, (_id, category) in enumerate(posts):
        _, distances = account_index.knnQuery(category, k=100)
        posts[index] = (_id, np.sum(distances))

    # Sort and return sorted ids. Lowest deviation is the best
    query_ids = [i for (i, _) in sorted(posts, key=lambda x: x[1])]
    return query_ids
