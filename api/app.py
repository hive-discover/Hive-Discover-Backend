from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware


from datetime import datetime
from threading import Thread
import sys, os
sys.path.append(os.getcwd() + "/.")
from config import *
from agents import AccessTokenManager, AccountSearch

from database import MongoDB
from api.models import *
from api import search, stats, accounts
from api.stats import add_statistic

# Create App, add CORS and Routers
app = FastAPI()#redoc_url=None, docs_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(search.router, prefix="/search", tags=["Searching"])
app.include_router(stats.router, prefix="/stats", tags=["Statistics"])
app.include_router(accounts.router, prefix="/accounts", tags=["Accounts"])


#   *** Endpoints ***

@app.get("/")
async def root(_ = Depends(add_statistic)):
    return {
        "status" : "ok",
        "info" : "Service is running",
        "database" : {
            "accounts" : await MongoDB.account_table.count_documents({}),
            "posts" : await MongoDB.post_table.count_documents({}),
            "stats" : await MongoDB.stats_table.count_documents({}),
            "banned" : await MongoDB.banned_table.count_documents({})
            }
        }


#   *** Managing ***

@app.on_event("startup")
async def on_startup():
    '''Init everything when Server is starting'''
    MongoDB.init_global(post_table=True, account_table=True, banned_table=True, stats_table=True)
    AccountSearch.init()
    Thread(target=AccountSearch.create_search_index, name="Account Indexer", daemon=True).start()
    AccessTokenManager.init()
    Thread(target=AccessTokenManager.run, name="AccessToken Manager", daemon=True).start()




async def on_shutdown():
    '''Stops everything'''
    pass


def start_server():
    import uvicorn
    uvicorn.run(app, host=HOST_IP, port=HOST_PORT)


if __name__ == '__main__':
   start_server()
 