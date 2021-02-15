from fastapi import APIRouter, Request, Depends

from hashlib import sha256
from datetime import datetime

from database import MongoDB
from api.models import *

router = APIRouter()


#   *** Depends Method ***
async def add_statistic(request : Request):
    '''Do statistic stuff'''
    # Prepare stats
    date = datetime.utcnow()
    anonym_host =  sha256(request.client.host.encode('utf-8')).hexdigest()
    url = str(request.url)
    
    # Enter in DB
    await MongoDB.stats_table.update_one({"date" : date.strftime("%d.%m.%Y")}, {"$inc" : {f"reports.{date.hour}.requests" : 1}}, upsert=True)
    await MongoDB.stats_table.update_one({"date" : date.strftime("%d.%m.%Y")}, {"$addToSet" : {f"reports.{date.hour}.connections" : anonym_host}})

    if "/search/posts" in url:
        await MongoDB.stats_table.update_one({"date" : date.strftime("%d.%m.%Y")}, {"$inc" : {f"reports.{date.hour}.post_queries" : 1}}, upsert=True)
    if "/search/accounts" in url:
        await MongoDB.stats_table.update_one({"date" : date.strftime("%d.%m.%Y")}, {"$inc" : {f"reports.{date.hour}.account_queries" : 1}}, upsert=True)
    if "/accounts/?" in url:
        await MongoDB.stats_table.update_one({"date" : date.strftime("%d.%m.%Y")}, {"$inc" : {f"reports.{date.hour}.account_data_queries" : 1}}, upsert=True)
    if "/accounts/feed" in url:
        await MongoDB.stats_table.update_one({"date" : date.strftime("%d.%m.%Y")}, {"$inc" : {f"reports.{date.hour}.feed_requests" : 1}}, upsert=True)


