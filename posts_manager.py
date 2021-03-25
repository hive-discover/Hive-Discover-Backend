from config import *
from typing import Iterable
from database import MongoDBAsync
from helper import helper
from account_manager import username_to_id

from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

from beem.comment import Comment
from beem.exceptions import ContentDoesNotExistsException

import secrets
import json
import asyncio
from datetime import datetime, timedelta

async def generate_post_ids(amount : int = 1) -> list:
    '''Generate some unused ids'''
    choosed = set([])
    while len(choosed) < amount:
        some_ids = [secrets.randbelow(2000000000) for _ in range(10 * amount * 2)]
        async for used_ids in MongoDBAsync.post_info.find({"_id" : {"$in" : some_ids}}, {"_id" : 1}):
            some_ids.remove(used_ids["_id"])
        
        for _id in some_ids:
            choosed.add(_id)

    return list(choosed)[0:amount]


#   *** Append Posts ***
async def remove_banned_listed(authors : list, permlinks : list, post_ids : list = None) -> list:
    '''Remove all banned/listed posts by settings _id to -1'''
    if not post_ids or len(post_ids) != len(authors):
        # If it is not setted or wrong
        post_ids = [0 for _ in authors]

    # Remove banned accounts
    async def remove_banned_accounts():
        async for banned in MongoDBAsync.banned.find({"name" : {"$in" : authors}}):
            for index, _ in enumerate(authors):
                if authors[index] == banned["name"]:
                    post_ids[index] = -1

    # Remove banned posts
    async def remove_banned_posts():
        async for banned in MongoDBAsync.banned.find({"author" : {"$in" : authors}, "permlink" : {"$in" : permlinks}}):
            for index, _ in enumerate(authors):
                if authors[index] == banned["author"] and permlinks[index] == banned["permlink"]:
                    post_ids[index] = -1

    # Find listed posts
    async def remove_listed_posts():
        async for post in MongoDBAsync.post_info.find({"author" : {"$in" : authors}, "permlink" : {"$in" : permlinks}}):
            for index, _ in enumerate(authors):
                if authors[index] == post["author"] and permlinks[index] == post["permlink"]:
                    post_ids[index] = post["_id"]
    
    # Filter all out
    await asyncio.gather(remove_banned_accounts(), remove_banned_posts(), remove_listed_posts())
    return post_ids

def remove_comments(posts : list, post_ids : list = None) -> list:
    '''Remove all comments by setting there post_ids to -1'''
    if not post_ids or len(post_ids) != len(posts):
        # If it is not setted or wrong
        post_ids = [0 for _ in posts]

    for index, _ in enumerate(posts):
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

    return post_ids

async def append_posts(posts : list) -> list:
    '''Insert all posts to DB and return _ids'''
    if len(posts) == 0:
        return []

    post_ids = [0 for _ in posts]
    open_ids = await generate_post_ids(len(posts))

    # Remove banned and comments
    post_ids = await remove_banned_listed([x["author"] for x in posts], [x["permlink"] for x in posts], post_ids)
    post_ids = remove_comments(posts, post_ids)

    # Prepare posts and texts
    post_infos, post_texts, post_data = [], [], []
    for index, post in enumerate(posts):
        if post_ids[index] != 0:
            # Banned, inside or something else
            continue

        # Prepare Body, Title and Tag_str
        body = ' '.join((helper.html_to_text(post["body"])))
        title = str(post["title"])        
        tag_str = ' '
        try:
            metadata = post["json_metadata"]
            if "tags" in metadata:
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                tag_str = ' '.join(metadata["tags"])
        except:
            pass
        
        # Set Timestamp
        if "created" in post:
            timestamp = post["created"]
        else:
            timestamp = datetime.utcnow()
        
        if datetime.date(timestamp + timedelta(days=100)) < datetime.date(datetime.utcnow()):
            post_ids[index] = -1
            continue

        if "nsfw" in tag_str or "cross-post" in tag_str:
            post_ids[index] = -1
            continue
        
        if "stop_discover" in tag_str or "stop_discover" in post["body"]:
            post_ids[index] = -1
            continue

        if len(body.split(' ')) < MIN_KNOWN_WORDS:
            post_ids[index] = -1
            continue
        
        post_ids[index] = open_ids[index]
        post_infos.append({"_id" : open_ids[index], "author" : post["author"], "permlink" : post["permlink"], "timestamp" : timestamp})
        post_texts.append({"_id" : open_ids[index], "title" : title, "body" : body, "tag_str" : tag_str, "timestamp" : timestamp})
        post_data.append({"_id" : open_ids[index], "categories" : None, "lang" : None, "timestamp" : timestamp})

    # Append all
    if len(post_data) > 0:

        try:         
            await MongoDBAsync.post_info.insert_many(post_infos)
            # If it reaches here, it was succesfull and the other things will also success
            await asyncio.wait([ MongoDBAsync.post_data.insert_many(post_data),
                                 MongoDBAsync.post_text.insert_many(post_texts)])
        except BulkWriteError:
            pass

    return post_ids


async def remove_posts(posts : list) -> None:
    '''Delete some posts. Posts can be _id, authors or tuple of author, permlink'''
    if len(posts) == 0:
        return

    if isinstance(posts[0], str):
        # Convet authors to ids
        posts = [p["_id"] async for p in MongoDBAsync.post_info.find({
                                        "author" : {"$in" : posts}})]
    elif isinstance(posts[0], tuple):
        if len(posts[0]) != 2:
            return

        # Convert tuples to ids
        authors, permlinks = [p[0] for p in posts], [p[1] for p in posts]
        posts = [p["_id"] async for p in MongoDBAsync.post_info.find({
                                        "author" : {"$in" : authors},
                                        "permlink" : {"$in" : permlinks}})]
    
    await asyncio.wait([
        MongoDBAsync.post_info.delete_many({"_id" : {"$in" : posts}}),
        MongoDBAsync.post_text.delete_many({"_id" : {"$in" : posts}}),
        MongoDBAsync.post_data.delete_many({"_id" : {"$in" : posts}}),
        # Remove also feed references
        MongoDBAsync.account_data.update_many({}, {"$pull" : {"feed" : {"$in" : posts}}})
    ])


#   *** Find Posts ***
async def authorperm_to_id(posts : list) -> list:
    '''Get _id field of posts. -1 if it does not exist. Posts has to be tuple(author, permlink)'''
    # Prepare
    post_ids = [-1 for _ in posts]
    authors = [author for author, _ in posts]
    permlinks = [permlink for _, permlink in posts]

    # Find and Set _ids
    async for post in MongoDBAsync.post_info.find({"author" : {"$in" : authors}, "permlink" : {"$in" : permlinks}}):
        for index, (author, permlink) in enumerate(posts):
            if author == post["author"] and permlink == post["permlink"]:
                post_ids[index] = post["_id"]

    return post_ids


#   *** Custom Operations ***
async def add_votes_to_posts(voters : list, posts : list):
    '''Append acc_votes to posts. len of votes and posts has to be equal. voters can be list of usernames or _ids. Posts can be list of tuple(author, permlink) or _id'''
    if len(voters) == 0 or len(posts) == 0 or len(posts) != len(voters):
        return

    # Test if posts are tuples and not _ids
    # --> Convert them
    if isinstance(posts[0], Iterable):
        posts = await authorperm_to_id(posts)
    
    # Test if voters are str's and not _ids
    # --> Convert them
    if isinstance(voters[0], str):
        voters = await username_to_id(voters)

    # Check if they are inside account_data (if they are analyzed) --> Make bulk list
    bulk_update = []
    async for account_data in MongoDBAsync.account_data.find({"_id" : {"$in" : voters}}):
        for voter_id, post_id in zip(voters, posts):
            if account_data["_id"] == voter_id and post_id >= 0:
                bulk_update.append(UpdateOne({"_id" : post_id}, {"$addToSet" : {"votes" : voter_id}}))
    
    # Make changes
    if len(bulk_update) > 0:
        try:
            await MongoDBAsync.post_data.bulk_write(bulk_update, ordered=False)
        except BulkWriteError:
            pass

async def clean_posts():
    '''Clean posts --> Make all collections equal'''
    # Look for all ids
    post_info_ids = [post["_id"] async for post in MongoDBAsync.post_info.find({})]
    post_data_ids = [post["_id"] async for post in MongoDBAsync.post_data.find({})]
    post_text_ids = [post["_id"] async for post in MongoDBAsync.post_text.find({})]

    # Everything is fine
    if len(post_info_ids) == len(post_data_ids) and len(post_info_ids) == len(post_text_ids):
        return

    # Find all posts, which are corrup
    corrupted_ids = []
    for _id in post_info_ids:
        if _id not in post_data_ids or _id not in post_text_ids:
            corrupted_ids.append(_id)
    del post_data_ids, post_info_ids, post_text_ids
    
    # Get all comments to reassign them
    posts = []
    async for post_info in MongoDBAsync.post_info.find({"_id" : {"$in" : corrupted_ids}}):
        try:
            posts.append(Comment(f'@{post_info["author"]}/{post_info["permlink"]}'))
        except ContentDoesNotExistsException:
            # Do nothing, it will be deleted afterwards
            continue

    # Delete everything corrupted
    await asyncio.wait([ MongoDBAsync.post_data.delete_many({"_id" : {"$in" : corrupted_ids}}),
                         MongoDBAsync.post_text.delete_many({"_id" : {"$in" : corrupted_ids}}),
                         MongoDBAsync.post_info.delete_many({"_id" : {"$in" : corrupted_ids}})])

    # Read all
    await append_posts(posts)

if __name__ == '__main__':
    async def do():
        MongoDBAsync.init_global(post_table=True, banned_table=True, account_table=True)
        await clean_posts()
        print(await append_posts([Comment("@action-chain/attention-we-released"),
             Comment("@action-chain/release-day-hive-discover")]))
    asyncio.run(do())

