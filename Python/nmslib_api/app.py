import sys, os
sys.path.append(os.getcwd() + "/.")
from config import *
from database import MongoDBAsync
from nmslib_api.feed_making import *

# If someone requests a feed, it is created here because the NodeJS Part redirects the request to this Endpoint.
# To achieve best perfomances we use FastAPI with Async. Multiprocessing is a bit complicated because of the NMSLIB Index which had to
# rebuild for every process

from fastapi import FastAPI, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status" : "ok", "info" : "Feed maker is running"}

@app.get("/similar")
async def find_similar(author : str = None, permlink : str = None, query_category : list = [], amount : int = 5, full_data : bool = False):
    '''Find similar posts by two ways: 1. give author and permlink or 2. categories. Amount specifies how much'''
    if author and permlink and len(query_category) == len(CATEGORIES):
        return {"status" : "failed", "info" : "Please send only an authorperm OR a query category!", "posts" : []}

    if author and permlink:
        # Find post_id
        post_info = await MongoDBAsync.post_info.find_one({"author" : author, "permlink" : permlink}, {"_id" : 1})
        if post_info:
            # Set categories
            post_data = await MongoDBAsync.post_data.find_one({"_id" : post_info["_id"]}, {"categories" : 1})
            if post_data:
                query_category = post_data["categories"]

    # Check query
    if len(query_category) != len(CATEGORIES):
        # Error
        return {"status" : "failed", "info" : "Query Categories Range is wrong. Correct your author/permlink or category input", "posts" : [], "target" : len(CATEGORIES), "got" : len(query_category)}

    # Got a good one --> find similar
    amount = min(abs(amount), 50)
    similar_ids = similar_by_category([query_category])[0]

    # Convert ids to authorperm. Copy the ids array and filter all integers (rest ids) out
    similar_posts = similar_ids[:]
    async for post in MongoDBAsync.post_info.find({"_id" : {"$in" : similar_ids}}):
        for index, p_id in enumerate(similar_ids):
            # Set post on right spot
            if post["_id"] == p_id:
                similar_posts[index] = {"author" : post["author"], "permlink" : post["permlink"]}
    similar_posts = [p for p in similar_posts if isinstance(p, dict)]

    # Check if full_data (post_text send with)
    if full_data:
        async for post in MongoDBAsync.post_text.find({"_id" : {"$in" : similar_ids}}):
            for index, p_id in enumerate(similar_ids):
                # Set post on right spot
                if post["_id"] == p_id:
                    similar_posts[index] = {**similar_posts[index], "post" : post}
    return similar_posts

@app.post('/feed')
async def get_feed(body = Body(None)):
    '''Create the feed for an Account'''
    # Process Input
    if not body or len(body) != 2 or "amount" not in body or "account_id" not in body:
        return {"status" : "failed", "msg" : body, "info" : "wrong parameter"}
    amount = min(abs(body["amount"]), 100)

    # Set background_task and return results
    return {"status" : "ok", "posts" : (await create_normal_feed(account_id=body["account_id"], amount=amount))}

@app.post('/sort/personalized')
async def post_sort_personalized(body = Body(None)):
    if not body or len(body) != 2 or "account_name" not in body or "query_ids" not in body:
        return {"status" : "failed", "msg" : body, "info" : "wrong parameter"}
    
    query_ids = await sort_ids_personalized(body["account_name"], body["query_ids"])
    return {"status" : "ok", "ids" : query_ids}


@app.on_event("startup")
async def on_startup():
    '''Init everything when Server is starting'''
    MongoDBAsync.init_global(post_table=True, account_table=True, banned_table=True)
    await create_search_index()




def start_server():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=FEED_API_PORT)

if __name__ == '__main__':
   start_server()
 