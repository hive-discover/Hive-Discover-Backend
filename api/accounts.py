from fastapi import APIRouter, Depends

from hivesigner.client import Client

from hashlib import sha256
import asyncio
import sys, os
sys.path.append(os.getcwd() + "/.")

from config import *
from database import MongoDBAsync
from agents import AccessTokenManager
from hive import AccountsManager
from api.models import *
from api.stats import add_statistic


router = APIRouter()

async def check_access_token(username : str, access_token : str):
    '''Check if access_token and username matches'''
    AccessTokenManager.open_tokens.append((username, access_token))

    # test first, if access_token is inside db
    acc = await MongoDBAsync.account_table.find_one({"name" : username})
    if acc and "access_token" in acc and acc["access_token"] == sha256(access_token.encode('utf-8')).hexdigest():
        # Inside db and correct
        return True

    # Token not in DB (maybe key in DB is to old, revoked or first time)
    # --> check    
    c = Client(access_token=access_token)
    data = c.me()
    return ("user" in data and data["user"] == username)



@router.get("/", responses={200 : {"model" : AccountData}, 401 : {"model" : Failed, "description" : "Access Token is invalid"}})
async def get_account_data(username : str, authorized = Depends(check_access_token),_ = Depends(add_statistic)):
    '''Get Account Data like categories, langs and more'''
    if authorized:
        return await AccountsManager.get_account_data(username)

    return {"status" : "failed", "info" : "Access Token does not match the Username", "msg" : {"username" : username}}

@router.get("/feed", responses={200 : {"model" : PostsResponse}, 401 : {"model" : Failed, "description" : "Access Token is invalid"}})
async def get_feed(username : str, max : int, authorized = Depends(check_access_token),_ = Depends(add_statistic)):
    '''Get Account Feed'''
    if authorized:
        posts = await AccountsManager.get_feed(username, max=max)
        return {"posts" : posts, "status" : "ok", "amount" : len(posts)}

    return {"status" : "failed", "info" : "Access Token does not match the Username", "msg" : {"username" : username}}

@router.get("/delete", responses={200 : {"model" : Succes}, 401 : {"model" : Failed, "description" : "Access Token is invalid"}})
async def delete(username : str, authorized = Depends(check_access_token),_ = Depends(add_statistic)):
    '''Get Account Feed'''
    if not authorized:
        return {"status" : "failed", "info" : "Access Token does not match the Username", "msg" : {"username" : username}}
    
    returns = await asyncio.gather( MongoDBAsync.account_table.delete_many({"name" : username}),
                                    MongoDBAsync.post_table.delete_many({"author" : username}))
    amount = returns[0].deleted_count + returns[1].deleted_count
    return {"status" : "ok", "info" : "Deleted everything", "msg" : {"username" : username, "amount" : amount}}
    
@router.get("/ban", responses={200 : {"model" : Succes}, 401 : {"model" : Failed, "description" : "Access Token is invalid"}})
async def ban(username : str, authorized = Depends(check_access_token),_ = Depends(add_statistic)):
    '''Get Account Feed'''
    if not authorized:
        return {"status" : "failed", "info" : "Access Token does not match the Username", "msg" : {"username" : username}}
    
    returns = await asyncio.gather( MongoDBAsync.account_table.delete_many({"name" : username}),
                                    MongoDBAsync.post_table.delete_many({"author" : username}),
                                    MongoDBAsync.banned_table.insert_one({"name" : username}))
    return {"status" : "ok", "info" : "banned", "msg" : {"username" : username}}


