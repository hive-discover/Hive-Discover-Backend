import pymongo
import motor.motor_asyncio

from config import *


class MongoDBAsync:
    def __init__(self, post_table : bool = False, account_table : bool = False, banned_table : bool = False, stats_table : bool = False) -> None:
        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_CONNECTION_STR)

        if post_table:
            self.post_table = self.mongo_client[DATABASE_NAME].posts # OLD
            self.post_info = self.mongo_client[DATABASE_NAME].post_info
            self.post_data = self.mongo_client[DATABASE_NAME].post_data
            self.post_text = self.mongo_client[DATABASE_NAME].post_text
        if account_table:
            self.account_table = self.mongo_client[DATABASE_NAME].accounts # Old
            self.account_info = self.mongo_client[DATABASE_NAME].account_info
            self.account_data = self.mongo_client[DATABASE_NAME].account_data
        if stats_table:
            self.stats_table = self.mongo_client[DATABASE_NAME].stats
        if banned_table:
            self.banned = self.mongo_client[DATABASE_NAME].banned
            
    @staticmethod
    def init_global(post_table : bool = False, account_table : bool = False, banned_table : bool = False, stats_table : bool = False) -> None:
        MongoDBAsync.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_CONNECTION_STR)

        if post_table:
            MongoDBAsync.post_table = MongoDBAsync.mongo_client[DATABASE_NAME].posts
            MongoDBAsync.post_info = MongoDBAsync.mongo_client[DATABASE_NAME].post_info
            MongoDBAsync.post_data = MongoDBAsync.mongo_client[DATABASE_NAME].post_data
            MongoDBAsync.post_text = MongoDBAsync.mongo_client[DATABASE_NAME].post_text
        if account_table:
            MongoDBAsync.account_table = MongoDBAsync.mongo_client[DATABASE_NAME].accounts
            MongoDBAsync.account_info = MongoDBAsync.mongo_client[DATABASE_NAME].account_info
            MongoDBAsync.account_data = MongoDBAsync.mongo_client[DATABASE_NAME].account_data
        if stats_table:
            MongoDBAsync.stats_table = MongoDBAsync.mongo_client[DATABASE_NAME].stats
        if banned_table:
            MongoDBAsync.banned = MongoDBAsync.mongo_client[DATABASE_NAME].banned

    
class MongoDB:
    def __init__(self, post_table : bool = False, account_table : bool = False, banned_table : bool = False, stats_table : bool = False) -> None:
        self.mongo_client = pymongo.MongoClient(MONGO_CONNECTION_STR)

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
        MongoDB.mongo_client = pymongo.MongoClient(MONGO_CONNECTION_STR)

        if post_table:
            MongoDB.post_info = MongoDB.mongo_client[DATABASE_NAME].post_info
            MongoDB.post_data = MongoDB.mongo_client[DATABASE_NAME].post_data
            MongoDB.post_text = MongoDB.mongo_client[DATABASE_NAME].post_text
        if account_table:
            MongoDB.account_table = MongoDB.mongo_client[DATABASE_NAME].accounts
            MongoDB.account_info = MongoDB.mongo_client[DATABASE_NAME].account_info
            MongoDB.account_data = MongoDB.mongo_client[DATABASE_NAME].account_data
        if stats_table:
            MongoDB.stats_table = MongoDB.mongo_client[DATABASE_NAME].stats
        if banned_table:
            MongoDB.banned_table = MongoDB.mongo_client[DATABASE_NAME].banned
