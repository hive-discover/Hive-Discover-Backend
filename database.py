import pymongo
import motor.motor_asyncio

from config import *


class MongoDBAsync:
    def __init__(self, post_table : bool = False, account_table : bool = False, banned_table : bool = False, stats_table : bool = False) -> None:
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(DATABASE_HOST, DATABASE_PORT)

        if post_table:
            self.post_table = self.mongo_client[DATABASE_NAME].posts
        if account_table:
            self.account_table = self.mongo_client[DATABASE_NAME].accounts
        if stats_table:
            self.stats_table = self.mongo_client[DATABASE_NAME].stats
        if banned_table:
            self.banned_table = self.mongo_client[DATABASE_NAME].banned
            
    @staticmethod
    def init_global(post_table : bool = False, account_table : bool = False, banned_table : bool = False, stats_table : bool = False) -> None:
        MongoDBAsync.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(DATABASE_HOST, DATABASE_PORT)

        if post_table:
            MongoDBAsync.post_table = MongoDBAsync.mongo_client[DATABASE_NAME].posts
        if account_table:
            MongoDBAsync.account_table = MongoDBAsync.mongo_client[DATABASE_NAME].accounts
        if stats_table:
            MongoDBAsync.stats_table = MongoDBAsync.mongo_client[DATABASE_NAME].stats
        if banned_table:
            MongoDBAsync.banned_table = MongoDBAsync.mongo_client[DATABASE_NAME].banned

    
class MongoDB:
    def __init__(self, post_table : bool = False, account_table : bool = False, banned_table : bool = False, stats_table : bool = False) -> None:
        self.mongo_client = pymongo.MongoClient(DATABASE_HOST, DATABASE_PORT)

        if post_table:
            self.post_table = self.mongo_client[DATABASE_NAME].posts
        if account_table:
            self.account_table = self.mongo_client[DATABASE_NAME].accounts
        if stats_table:
            self.stats_table = self.mongo_client[DATABASE_NAME].stats
        if banned_table:
            self.banned_table = self.mongo_client[DATABASE_NAME].banned

    @staticmethod
    def init_global(post_table : bool = False, account_table : bool = False, banned_table : bool = False, stats_table : bool = False) -> None:
        MongoDB.mongo_client = pymongo.MongoClient(DATABASE_HOST, DATABASE_PORT)

        if post_table:
            MongoDB.post_table = MongoDB.mongo_client[DATABASE_NAME].posts
        if account_table:
            MongoDB.account_table = MongoDB.mongo_client[DATABASE_NAME].accounts
        if stats_table:
            MongoDB.stats_table = MongoDB.mongo_client[DATABASE_NAME].stats
        if banned_table:
            MongoDB.banned_table = MongoDB.mongo_client[DATABASE_NAME].banned
