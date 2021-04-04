from helper import helper
from agents import *
from config import *
from database import MongoDBAsync

from beem import Hive 
from beem.nodelist import NodeList
from beem.blockchain import Blockchain
from beem.exceptions import AccountDoesNotExistsException
from beem.comment import Comment
from beem.exceptions import ContentDoesNotExistsException
from beem.account import Account
import numpy as np

from pymongo import MongoClient

from datetime import datetime
import time
import json
import secrets, math
import asyncio

instance = Hive(node=NodeList().get_nodes(hive=True))


class PostsManager():
    def __init__(self) -> None:
        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT, username=DATABASE_NAME, password=DATABASE_PASSWORD)
        self.post_table = self.mongo_client[DATABASE_NAME].posts
        self.banned_table = self.mongo_client[DATABASE_NAME].banned

    @staticmethod
    def append_post(post_table, banned_table, post, timestamp = None, update = False, helper = None, insert_in_db=True) -> int:
        '''Process a Hive Post and add it to the Database. Return Post_ID, when append. -1, when no less words, already inside, it fails or it is banned.
        When update is true and the post exists, it will update the old document'''

        # Check if post or account is banned
        if banned_table.find_one({"author" : post["author"], "permlink" : post["permlink"]}) or banned_table.find_one({"name" : post["author"]}):
            return -1

        # Check existence
        inside_post = post_table.find_one({"author" : post["author"], "permlink" : post["permlink"]})
        if inside_post and update is False:
            # Already exists and no update
            return inside_post["post_id"]

       # while not statics.FASTTEXT_MODEL or not statics.TEXTCNN_MODEL:
           # time.sleep(1)
        if not helper:
            helper = helper.helper()

        # Make text
        metadata = post["json_metadata"]
        tag_str = ' '
        if "tags" in metadata:
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            tag_str = ' '.join(metadata["tags"])

        body = ' '.join((helper.html_to_text(post["body"])))
        title = str(post["title"])

        # test, if nsfw (not save for work) or stop item inside
        if "nsfw" in tag_str or "stop_discover" in tag_str or "stop_discover" in post["body"]:
            return -1

        #text = helper.pre_process_text(title + ". " + body + ". " + tag_str)
        lang = None #statics.LANG_DETECTOR.predict_lang(text)
        #tok_text = helper.tokenize_text(text)

        # Categorize Post later
        categories_doc = None #PostsCategory.categorize_post(tok_text)
      
        if timestamp is None:
            timestamp = datetime.utcnow()

        post_obj = {
            "author" : post["author"],
            "permlink" : post["permlink"],
            "timestamp" : timestamp,
            "categories_doc" : categories_doc,
            "lang" : lang,
            "body" : body,
            "title" : title,
            "tags" : tag_str
            }

        if not inside_post:
            # Create unused post_id
            while "post_id" not in post_obj or post_table.find_one({"post_id" : post_obj["post_id"]}):
                post_obj["post_id"] = secrets.randbelow(2000000000)
        else:
            # Retake post_id
            post_obj["post_id"] = inside_post["post_id"]

        if not insert_in_db:
            return post_obj

        if not inside_post:
            # Insert
            post_table.insert_one(post_obj)
            return post_obj["post_id"]
        else:
            # Update
            post_table.update_one({"post_id" : inside_post["post_id"]}, {"$set" : post_obj})
            return inside_post["post_id"] 

    @staticmethod   
    def append_posts(post_table, banned_table, posts, timestamp = None, update = False, helper = None) -> list:
        '''Appends a lot of posts to the DB. Returns post id or -1 when fails'''
        all_posts = [PostsManager.append_post(post_table, banned_table, post, timestamp=timestamp, update=update, helper=helper, insert_in_db=False) for post in posts]

        # Find all unentered posts
        # When post_obj is a dict, it is a new post
        # Then, also set post_id in all_posts list
        enter_posts = []
        for index, post in enumerate(all_posts):
            if isinstance(post, dict):
                enter_posts.append(post)
                all_posts[index] = post["post_id"]

        # Insert and return
        if len(enter_posts) > 0:
            post_table.insert_many(enter_posts)
        return all_posts

    @staticmethod
    def append_post_gentle(post_table, banned_table, author, permlink, update = False, helper = None) -> int:
        '''Check if a post exist and then returns it id or get post from HIVE and append it'''
        # Check existence
        inside_post = post_table.find_one({"author" : author, "permlink" : permlink})
        if inside_post:
            # Already exists
            return inside_post["post_id"]

        # Download post, append it and return id
        try:
            post = Comment(f"@{author}/{permlink}")
            post_id = PostsManager.append_post(post_table, banned_table, post, post["created"], update=update, helper=helper)
            return post_id
        except ContentDoesNotExistsException:
            return -1

    @staticmethod
    async def append_async_posts(posts, timestamp = None) -> list:
        '''Appends all posts but async'''
        authors = [x["author"] for x in posts]
        permlinks = [x["permlink"] for x in posts]
        post_ids = [0 for _ in posts]

        async def remove_banned_accounts():
            async for banned in MongoDBAsync.banned_table.find({"name" : {"$in" : authors}}):
                for index, _ in enumerate(authors):
                    if authors[index] == banned["name"]:
                        post_ids[index] = -1

        # Remove banned posts
        async def remove_banned_posts():
            async for banned in MongoDBAsync.banned_table.find({"author" : {"$in" : authors}, "permlink" : {"$in" : permlinks}}):
                for index, _ in enumerate(authors):
                    if authors[index] == banned["author"] and permlinks[index] == banned["permlink"]:
                        post_ids[index] = -1

        # Find listed posts
        async def remove_listed_posts():
            async for post in MongoDBAsync.post_table.find({"author" : {"$in" : authors}, "permlink" : {"$in" : permlinks}}):
                for index, _ in enumerate(authors):
                    if authors[index] == post["author"] and permlinks[index] == post["permlink"]:
                        post_ids[index] = post["post_id"]
        
        # Filter all out
        await asyncio.gather(remove_banned_accounts(), remove_banned_posts(), remove_listed_posts())

        # Remove all Comments (if any are there)
        for index, _ in enumerate(authors):
            if isinstance(posts[index], dict):
                try:
                    if posts[index]["parent_author"] != "":
                        post_ids[index] = -1
                except:
                    pass
                
            if isinstance(posts[index], Comment):            
                try:
                    if posts[index].parent_author != "":
                        post_ids[index] = -1
                except:
                    pass

        for index, _ in enumerate(authors):
            if post_ids[index] == -1:
                continue
            
            post = posts[index]
            metadata = post["json_metadata"]
            tag_str = ' '
            try:
                if "tags" in metadata:
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    tag_str = ' '.join(metadata["tags"])
            except:
                pass

            body = ' '.join((helper.html_to_text(post["body"])))
            title = str(post["title"])

            # test, if nsfw (not save for work) or cross-post
            if "nsfw" in tag_str or "cross-post" in tag_str:
                post_ids[index] = -1
                continue
            
            # test, if stop item is inside
            if "stop_discover" in tag_str or "stop_discover" in post["body"]:
                post_ids[index] = -1
                continue

            # test length
            if len(body.split(' ')) < 15:
                post_ids[index] = -1
                continue

            # Lang and Categories will later be setted
            lang = None
            categories_doc = None 

            if post_ids[index] == 0:
                while post_ids[index] == 0 or await MongoDBAsync.post_table.find_one({"post_id" : post_ids[index]}):
                    post_ids[index] = secrets.randbelow(2000000000)

            if "created" in post:
                timestamp = post["created"]
            if timestamp is None:
                timestamp = datetime.utcnow()

            post_obj = {
                "author" : post["author"],
                "permlink" : post["permlink"],
                "post_id" : post_ids[index],
                "timestamp" : timestamp,
                "categories_doc" : categories_doc,
                "lang" : lang,
                "body" : body,
                "title" : title,
                "tags" : tag_str
                }
            
            try:
                await MongoDBAsync.post_table.update_many({"author" : post["author"], "permlink" : post["permlink"]},
                                    {"$set" : post_obj}, upsert=True)
            except:
                # Something wierd happend but it is really inside
                pass


        return post_ids

    @staticmethod
    async def append_async_posts_gentle(authors : list, permlinks : list) -> list:
        '''Append Posts to DB when it does not exist, it will be downloaded. Returns a list of post_ids''' 
        post_ids = [0 for _ in authors]
        query = [{"author" : authors[index], "permlink" : permlinks[index]} for index, _ in enumerate(authors)]

        # Find all posts, which are inside
        async for post in MongoDBAsync.post_table.find({"$or" : query}):
            for index, _ in enumerate(authors):
                if authors[index] == post["author"] and permlinks[index] == post["permlink"]:
                    post_ids[index] = post["post_id"]

        # Download all other posts and append them
        posts = []
        selected_indexes = []
        for index, _id in enumerate(post_ids):
            if _id == 0:
                try:
                    posts.append(Comment(f"{authors[index]}/{permlinks[index]}"))
                    selected_indexes.append(index)
                except ContentDoesNotExistsException:
                    post_ids[index] = -1

        inserted_posts = await PostsManager.append_async_posts(posts)
        for counter, index in enumerate(selected_indexes):
            post_ids[index] = inserted_posts[counter]
        return post_ids

            

class AccountsManager():
    @DeprecationWarning
    def __init__(self) -> None:
        self.chain = Blockchain(blockchain_instance=instance)

        self.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT, username=DATABASE_NAME, password=DATABASE_PASSWORD)
        self.account_table = self.mongo_client[DATABASE_NAME].accounts
        self.post_table = self.mongo_client[DATABASE_NAME].posts
        self.banned_table = self.mongo_client[DATABASE_NAME].banned

        self.open_username = []
        self.running_analyses = [] # account_names
        self.running_feed_makings = [] # account_names

    @staticmethod
    def init() -> None:
        AccountsManager.mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT, username=DATABASE_NAME, password=DATABASE_PASSWORD)
        AccountsManager.account_table = AccountsManager.mongo_client[DATABASE_NAME].accounts
        AccountsManager.post_table = AccountsManager.mongo_client[DATABASE_NAME].posts
        AccountsManager.banned_table = AccountsManager.mongo_client[DATABASE_NAME].banned

    @staticmethod
    async def get_account_data(account : str) -> dict:
        '''Creates a dict from data inside DB. Dict contains something like: loading state, categories, last_analyze'''
        # Check if banned
        if await MongoDBAsync.banned_table.find_one({"name" : account}):
            # Delete data, if anything is left
            await MongoDBAsync.account_table.delete_many({"name" : account})
            return {"status" : "failed", "info" : "account is banned", "banned" : True, "username" : account}

        acc = await MongoDBAsync.account_table.find_one({"name" : account})
        if not acc:
            # account is not listed
            return {"status" : "failed", "info" : "account is not available", "username" : account}

        return_dict = {"status" : "ok", "info" : "account is available", "username" : account}

        if "loading" in acc:
            return_dict["loading"] = acc["loading"]   
        if "last_analyze" in acc:
            return_dict["last_analyze"] = acc["last_analyze"]
        if "posts" in acc:
            return_dict["posts_len"] = len(acc["posts"])
        if "votes" in acc:
            return_dict["votes_len"] = len(acc["votes"])


        categories, languages = await AccountsManager.get_account_cats_and_lang(acc)
        return_dict["categories"] = categories
        return_dict["language"] = languages    

        return return_dict

    @staticmethod
    async def get_account_cats_and_lang(acc : dict) -> tuple:
        '''Get the Posts and lang of an account and return it as a tuple of like ({"categories"}, {"lang"})'''
        if acc is None or len(acc) == 0:
            return (None, None)

        open_ids = []
        if "posts" in acc:
            open_ids = open_ids + acc["posts"]
        if "votes" in acc:
            open_ids = open_ids + acc["votes"]

        # Get all categories and langs from posts
        categories = np.array([])
        languages = []
        now_date = datetime.utcnow()
        async for post in MongoDBAsync.post_table.find({"post_id" : {"$in" : open_ids}}):
            if post and post["categories_doc"] is not None:
                # Post is ok and has categories
                post_categories = np.array(post["categories_doc"])
                languages.append(post["lang"])

                # Own-posts count double
                if post["post_id"] in acc["posts"]:
                    post_categories = post_categories * 2
                    languages.append(post["lang"])

                # Decrease value by the amount of month between now and the post
                # Get days between two dates and divide by 30.5 (average month len)
                # Then multiply all post_categories with square root from (0.9^x)
                monthes_between = (now_date - post["timestamp"]).days / 30.5
                post_categories = post_categories * math.sqrt(pow(0.9, monthes_between))

                if len(categories) == 0:
                    categories = post_categories
                else:
                    categories = np.add(categories, post_categories)
        
        # Filter Language
        filtered = []
        for post_lang in languages:
            if not post_lang:
                continue
            
            for lang in post_lang:
                if isinstance(lang, dict):
                    for filtered_lang in filtered:
                        if filtered_lang["lang"] == lang["lang"]:
                            # Found lang already inside --> add
                            filtered_lang["x"] += lang["x"]
                            break
                    else:
                        # Insert new lang
                        filtered.append(lang)

        # Calc percentages for Languages. Only langs above 20% got listed
        total = np.sum([lang["x"] for lang in filtered])
        if total > 0:
            languages = [{"label" : item["lang"], "value" : (item["x"]/total)} for item in filtered]
            languages = [item for item in languages if item["value"] >= 0.2]
        else:
            languages = []

        # Calc percentages for Categories
        total = np.sum(categories)
        if total > 0:
            categories = [(value/total) for value in categories]

        # Combine values with labels, sort it then by value and append as dict
        combined_cats = []
        for index, value in enumerate(categories):
            combined_cats.append({"value" : value, "label" : CATEGORIES[index][0]})
        categories = sorted(combined_cats, key=lambda x: x["value"], reverse=True)

        return (categories, languages)

    @staticmethod
    async def get_feed(account : str, max=21, full = False, feed_making_request = True) -> list:
        '''Gets a feed and returns that as an list. If account is not listed, it will just return en empty list. Minimun amount is 3. When full is True, it will also return Title, Body and Tags'''
        acc = await MongoDBAsync.account_table.find_one({"name" : account})
        if not acc:
            # Account does not exist --> Insert
            await AccountsManager.add_account(account, data={"analyze" : True})
            return []

        # Make Feed Request and start analyzing when it is never analyzed
        if "last_analyze" not in acc:
            await MongoDBAsync.account_table.update_one({"name" : account}, {"$set" : {"analyze" : True}})
        if feed_making_request:
            await MongoDBAsync.account_table.update_one({"name" : account}, {"$set" : {"make_feed" : True}})      

        # Is Empty, or never made
        if "feed" not in acc or len(acc["feed"]) == 0:
            return []

        # Minimize list (min. 3). If no feed is there, it is automatically zero
        posts = acc["feed"]
        while len(posts) > max and len(posts) > 3:
            posts.remove(secrets.choice(posts))
        
        # Remove them from account object in DB and combine posts with author-permlink
        await MongoDBAsync.account_table.update_one({"name" : account}, {"$pull" : {"feed" : {"$in" : posts}}})

        combined_posts = []
        async for post in MongoDBAsync.post_table.find({"post_id" : {"$in" : posts}}):
            item = {"author" : post["author"], "permlink" : post["permlink"]}
            if full and "body" in post:
                item["body"] = post["body"]
            if full and "title" in post:
                item["title"] = post["title"]
            if full and "tags" in post:
                item["tags"] = post["tags"].split(' ')

            if "lang" in post and not post["lang"] is None and isinstance(post["lang"], dict):
                item["language"] = [item["lang"] for item in post["lang"]]
            combined_posts.append(item)
        return combined_posts

    @staticmethod
    @DeprecationWarning
    async def make_feed(account : str, delete_old = False, stop_event = None):
        '''Create a feed for an analyzed Account'''
        await MongoDBAsync.account_table.update_one({"name" : account}, {"$unset" : {"make_feed" : ""}})
        import secrets

        acc_langs = []
        last_posts_count, last_votes_count = 0, 0
        while not stop_event.is_set():
            acc = AccountsManager.account_table.find_one({"name" : account})
            if not acc:
                # no account -> something went wrong
                break

            if ("posts" not in acc or "votes" not in acc) or (len(acc["posts"]) == 0 and len(acc["votes"]) == 0):
                # Put analyze request into DB and wait a bit
                await AccountsManager.account_table.update_one({"name" : account}, {"$set" : {"analyze" : True}})
                time.sleep(1)
                continue
            
            # Get Lang from Account (Only when it is empty or new votes/posts are available) and make it as a 
            # simple List. From [{...}, {...}] to ["...", "..."]
            if len(acc_langs) == 0 or last_posts_count != len(acc["posts"]) or last_votes_count != len(acc["votes"]):
                _, acc_langs = await AccountsManager.get_account_cats_and_lang(acc=acc)
                acc_langs = [item["lang"] for item in acc_langs]

            acc_posts, acc_votes = acc["posts"], acc["votes"]         
            if not "feed" in acc:
                # Setup, only local
                acc["feed"] = []

            feed_list = acc["feed"]
            if len(feed_list) >= ACCOUNT_MIN_FEED_LEN and delete_old is False:
                # Succes, feed_list is full
                break

            # Get Post Ids (similar)
            similar_posts = []
            if len(acc_posts) > 0:
                # Get similar posts like his own
                own_post_ids = [secrets.choice(acc_posts) for x in range(0, secrets.randbelow(len(acc_posts)))]
                similar_posts += PostsCategory.search(own_post_ids, k=30)["results"]
                
            if len(acc_votes) > 0:
                # Get similar posts like he voted
                voted_post_ids = [secrets.choice(acc_votes) for x in range(0, secrets.randbelow(len(acc_votes)))]
                similar_posts += PostsCategory.search(voted_post_ids, k=20)["results"]

            # Extrace Similar Post IDs
            open_ids = []
            for item in similar_posts:
                # Enter all in open_ids
                open_ids += [result["post_id"] for result in item["results"]]

            # Check if not liked or not own posts
            for _id in open_ids:
                if _id in acc_votes:
                    open_ids.remove(_id)
                if _id in acc_posts:
                    open_ids.remove(_id)

            
            # Check langs from the posts: Query for id and lang (it will only return matches)
            relevant_posts = await AccountsManager.post_table.find({"post_id" : {"$in" : open_ids}, "lang" : {"$elemMatch" : {"lang" : {"$in" : acc_langs}}}})
            open_ids = [item["post_id"] for item in relevant_posts]

            if len(open_ids) == 0:
                continue
            
            # Check if old data should be deleted
            if delete_old:
                await AccountsManager.account_table.update_one({"name" : account}, {"$set" : {"feed" : []}})
                delete_old = False

            # Enter some random ones
            amount = secrets.randbelow(min([len(open_ids), ACCOUNT_MIN_FEED_LEN]))
            AccountsManager.account_table.update_one({"name" : account}, {"$addToSet" : {"feed" : {"$each" :  [secrets.choice(open_ids) for _ in range(amount)]}}})

    @staticmethod
    def delete_account(account : str) -> dict:
        '''Delete everything from an account'''
        posts_deleted = AccountsManager.post_table.delete_many({"author" : account})
        accounts_deleted = AccountsManager.account_table.delete_many({"name" : account})
        return {"status" : "ok", "accounts" : accounts_deleted.deleted_count, "posts" : posts_deleted.deleted_count}

    @staticmethod
    async def add_account(account : str, data = None):
        '''Checks if an account is banned. If not, it will be added in the DB. If it was successfully, it $set's the data to this account'''
        # Check if already inside
        if await MongoDBAsync.account_table.find_one({"name" : account}):
            return

        # Check if banned
        if await MongoDBAsync.banned_table.find_one({"name" : account}):
            return

        # Add to db and get acc_bio
        await MongoDBAsync.account_table.insert_one({"name" : account})
        if data:
            MongoDBAsync.account_table.update_one({"name" : account}, {"$set" : data})

    @staticmethod
    async def analyze_account(account : str):
        '''Analyzes an account'''
        # Check if banned
        if await MongoDBAsync.banned_table.find_one({"name" : account}):
            return        
        hive_acc = Account(account)

        # Get all operations and set loading            
        operations = hive_acc.history_reverse(only_ops=['comment', 'vote'])
        max = np.sum(1 for _ in operations)
        operations = hive_acc.history_reverse(only_ops=['comment', 'vote'])

        await MongoDBAsync.account_table.update_one({"name" : account}, {"$set" : {"loading" : { "current" : 0, "max" : max} }})
        await MongoDBAsync.account_table.update_one({"name" : account}, {"$set" : {"posts" : [], "votes" : [] }})

        # Analyze
        for index, operation in enumerate(operations):
            await MongoDBAsync.account_table.update_one({"name" : account}, {"$set" : {"loading" : { "current" : (index + 1), "max" : max} }})
            
            # Test if vote
            if operation["type"] == "vote":
                if operation["voter"] == account and operation["voter"] != operation["author"]:
                    # Vote from him to a foreign post
                    post_ids = await PostsManager.append_async_posts_gentle(authors=[operation['author']], permlinks=[operation['permlink']])
                    if len(post_ids) > 0 and post_ids[0] >= 0:
                        # Append to list
                        await MongoDBAsync.account_table.update_one({"name" : account}, {"$push" : {"votes" : post_ids[0] }})

            
            # Test if comment
            if operation["type"] == "comment":
                if operation["author"] == account:
                    # He wrote the Post and is no comment
                    if operation["parent_author"] == '':
                        post_ids = await PostsManager.append_async_posts_gentle(authors=[operation['author']], permlinks=[operation['permlink']])
                        if len(post_ids) > 0 and post_ids[0] >= 0:
                            # Append to list
                            await MongoDBAsync.account_table.update_one({"name" : account}, {"$push" : {"posts" : post_ids[0] }})

        # Ending
        await MongoDBAsync.account_table.update_one({"name" : account}, {"$set" : {"last_analyze" : datetime.utcnow(), "loading" : False, "make_feed" : True}})

    @DeprecationWarning
    def add_accountd(self, username : str):
        '''Append username to list to check if it is inside DB'''
        self.open_username.append(username)
    
    @DeprecationWarning
    def refresh_account_bio(self, username : str, metadata = {}) -> None:
        '''Refreshes account bio, metadata is optional (it will be getted)'''
        if metadata == {}:   
            # Try get Account, catch delete Acc from DB      
            try:
                account = Account(username)
            except AccountDoesNotExistsException:
                self.account_table.delete_one({"name" : username})
                return
         
            if "json_metadata" in account:
                metadata = account["json_metadata"]
            if "posting_json_metadata" in account:
                metadata = account["posting_json_metadata"]
            
        # Try to decode, catch it was deleted
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}

        if "profile" in metadata:
            metadata = metadata["profile"]

        # Retrieve all possible data
        profile = {}        
        if "name" in metadata:
            profile["name"] = metadata["name"]
        if "about" in metadata:
            profile["about"] = metadata["about"]
        if "location" in metadata:
            profile["location"] = metadata["location"]

        # Enter. Also if nothing is in profile because maybe user deleted 
        self.account_table.update_one({"name" : username}, {"$set" : {"profile" : profile}})

    @DeprecationWarning
    def run(self) -> None:
        '''Endless Thread to manage Accounts'''
        while 1:
            # Check Open Usernames
            while len(self.open_username) > 0:
                current_username = self.open_username[0]
                self.open_username.pop(0)

                # Check if already inside
                if self.account_table.find_one({"name" : current_username}):
                    continue

                # Check if banned
                if self.banned_table.find_one({"name" : current_username}):
                    continue

                # Add to db and get acc_bio
                self.account_table.insert_one({"name" : current_username})
                self.refresh_account_bio(current_username)

            time.sleep(1)

    @DeprecationWarning
    def add_account_vote(self, username : str, author : str, permlink : str) -> None:
        '''Append a vote to an Account, if it is analyzed. If it is not listed, it will append to open_usernames'''
        account = self.account_table.find_one({"name" : username})
        if not account or "votes" not in account:
            # not an account, maybe it were never analyzed, maybe it was delted, maybe it is banned
            self.open_username.append(username)
            return

        # Find voted Post
        post = self.post_table.find_one({"author" : author, "permlink" : permlink})
        if not post:
            # It is not listed, maybe deleted, maybe comment, maybe nsfw or something else, Just abort
            return

        self.account_table.update_one({"name" : username}, {"$push" : {"votes" : post["post_id"] }}, upsert=True)       

    @DeprecationWarning
    def add_account_post(self, username : str, post_id : int) -> None:
        '''Append a post to an analyzed account'''
        if post_id < 0:
            return

        # Find Account
        account = self.account_table.find_one({"name" : username})
        if not account or "votes" not in account:
            # not an account, maybe it were never analyzed, maybe it was delted, maybe it is banned
            self.open_username.append(username)
            return

        # Update
        self.account_table.update_one({"name" : username}, {"$push" : {"posts" : post_id}}, upsert=True)  
         
    