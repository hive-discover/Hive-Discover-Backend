from fastapi import APIRouter, Request, Depends

from hashlib import sha256
from datetime import datetime

from database import MongoDBAsync
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
    await MongoDBAsync.stats_table.update_one(
        {"date" : date.strftime("%d.%m.%Y")}, 
        {"$addToSet" : {f"reports.{date.hour}.connections" : anonym_host},
        "$inc" : {f"reports.{date.hour}.requests" : 1}})

    if "/search/posts" in url:
        await MongoDBAsync.stats_table.update_one({"date" : date.strftime("%d.%m.%Y")}, {"$inc" : {f"reports.{date.hour}.post_queries" : 1}}, upsert=True)
    if "/search/accounts" in url:
        await MongoDBAsync.stats_table.update_one({"date" : date.strftime("%d.%m.%Y")}, {"$inc" : {f"reports.{date.hour}.account_queries" : 1}}, upsert=True)
    if "/accounts/?" in url:
        await MongoDBAsync.stats_table.update_one({"date" : date.strftime("%d.%m.%Y")}, {"$inc" : {f"reports.{date.hour}.account_data_queries" : 1}}, upsert=True)
    if "/accounts/feed" in url:
        await MongoDBAsync.stats_table.update_one({"date" : date.strftime("%d.%m.%Y")}, {"$inc" : {f"reports.{date.hour}.feed_requests" : 1}}, upsert=True)

@router.get("/")
async def get_stats(date : Optional[str] = None):
    if date is None:
        date = datetime.utcnow()
    if isinstance(date, str):
        date = datetime.strptime(date, "%d.%m.%Y")
    if not isinstance(date, datetime):
        return {"status" : "failed", "info" : "no datetime object is given", "msg" : {"input" : date}}

    stat = await MongoDBAsync.stats_table.find_one({"date" : date.strftime("%d.%m.%Y")})

    # Make Hour Report
    reports = []
    for hour in range(23):
        if stat and str(hour) in stat["reports"]:
            # Hour is inside
            data = stat["reports"][str(hour)]
            data["hour"] = hour
            if "connections" in data and isinstance(data["connections"], list):
                # Process list of connection hashes to int
                data["connections"] = len(data["connections"])
            reports.append(data)
    
    return {"date" : date, "reports" : reports, "status" : "ok"}

