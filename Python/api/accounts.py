from fastapi import APIRouter, Depends

from hivesigner.client import Client

from hashlib import sha256
import asyncio
import sys, os
sys.path.append(os.getcwd() + "/.")

import account_manager, account_processing
import posts_manager
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
    acc = await MongoDBAsync.account_info.find_one({"name" : username})
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
    account_info = (await account_manager.get_account_info([username]))[0]
    if not account_info:
        # Account does not exist
        banned = await MongoDBAsync.banned.find_one({"name" : username})
        if banned:
            # Account is banned
            return {"status" : "banned", "info" : "account is banned", "msg" : {"username" : username}}
        return {"status" : "failed", "info" : "account is not listed", "msg" : {"username" : username}}

    # Account exist. Test if it is analyzed
    if authorized:
        account = (await account_manager.get_account_data([username]))[0]
        if not account:
            # Account is not analyzed
            return {"status" : "failed", "info" : "account is not analyzed", "msg" : {"username" : username}}

        cats, langs = await account_processing.get_account_cats_langs(username)
        return {"status" : "ok",
                "categories" : cats, 
                "language" : langs, 
                "loading" : ("loading" in account and account["loading"] == True)}

    return {"status" : "failed", "info" : "Access Token does not match the Username", "msg" : {"username" : username}}

@router.get("/feed", responses={200 : {"model" : PostsResponse}, 401 : {"model" : Failed, "description" : "Access Token is invalid"}})
async def get_feed(username : str, max : int, authorized = Depends(check_access_token),_ = Depends(add_statistic)):
    '''Get Account Feed'''
    if authorized:
        posts = await account_processing.get_feed(username, amount=max)
        return {"posts" : posts, "status" : "ok", "amount" : len(posts)}

    return {"status" : "failed", "info" : "Access Token does not match the Username", "msg" : {"username" : username}}

@router.get("/delete", responses={200 : {"model" : Succes}, 401 : {"model" : Failed, "description" : "Access Token is invalid"}})
async def delete(username : str, authorized = Depends(check_access_token),_ = Depends(add_statistic)):
    '''Get Account Feed'''
    if not authorized:
        return {"status" : "failed", "info" : "Access Token does not match the Username", "msg" : {"username" : username}}
    
    result = await account_manager.delete_accounts([username])
    await posts_manager.remove_posts([username])
    if result:
        return {"status" : "ok", "info" : "Deleted everything", "msg" : {"username" : username}}
    return {"status" : "failed", "info" : "Something went wrong", "msg" : {"username" : username}}
   
@router.get("/ban", responses={200 : {"model" : Succes}, 401 : {"model" : Failed, "description" : "Access Token is invalid"}})
async def ban(username : str, authorized = Depends(check_access_token),_ = Depends(add_statistic)):
    '''Get Account Feed'''
    if not authorized:
        return {"status" : "failed", "info" : "Access Token does not match the Username", "msg" : {"username" : username}}
    
    result = await account_manager.ban_accounts([username])
    if result:
        return {"status" : "ok", "info" : "banned", "msg" : {"username" : username}}
    return {"status" : "failed", "info" : "Something went wrong", "msg" : {"username" : username}}


