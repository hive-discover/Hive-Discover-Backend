from database import MongoDBAsync
from config import *
from account_manager import append_accounts, get_account_info

import numpy as np

async def get_account_cats_langs(account_name : str = None, account_id : int = -1) -> tuple:
    '''Calc the categories and langs by an account. One parameter has to be setted. Return as (cats, langs)'''
    if account_name is None and account_id == -1:
        return (None, None)

    # Get Account Info
    acc = None
    if account_name:
        acc = (await get_account_info([account_name]))[0]
    if account_id > -1 and not acc:
        acc = (await get_account_info([account_id]))[0]

    if not acc:
        # Account does not exist
        return (None, None)
    account_name, account_id = acc["name"], acc["_id"]

    # Get Post_IDs from his own posts
    own_post_ids = [post["_id"] async for post in MongoDBAsync.post_info.find({"author" : account_name})]

    # Retrieve all data from db
    categories, langs = np.array([]), []
    async for post in MongoDBAsync.post_data.find({"$or" : [{"votes" : account_id}, {"_id" : {"$in" : own_post_ids}}]}):
        if not post or post["categories"] is None or post["categories"] is False or post["lang"] is None:
            continue
        post_cats, post_langs = np.array(post["categories"]), post["lang"]
        

        if post["_id"] in own_post_ids:
            # His own post --> counts double
            post_cats = post_cats * 2
            langs.append(post_langs)
        
        langs.append(post_langs)
        if len(categories) == 0:
            categories = post_cats[:]
        else:
            categories = np.add(categories, post_cats)

    # Filter Language
    filtered = []
    for post_lang in langs:
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
        langs = [{"label" : item["lang"], "value" : (item["x"]/total)} for item in filtered]
        langs = [item for item in langs if item["value"] >= 0.2]
    else:
        langs = []

    # Calc percentages for Categories
    total = np.sum(categories)
    if total > 0:
        categories = [(value/total) for value in categories]

    # Combine values with labels, sort it then by value and append as dict
    combined_cats = []
    for index, value in enumerate(categories):
        combined_cats.append({"value" : value, "label" : CATEGORIES[index][0]})
    categories = sorted(combined_cats, key=lambda x: x["value"], reverse=True)

    return (categories, langs)

async def get_feed(account_name : str = None, account_id : int = -1, amount : int = 25) -> list:
    '''Get a feed list for an account'''
    if account_name is None and account_id == -1:
        return []

    # Get Account Info
    acc = None
    if account_name:
        acc = (await get_account_info([account_name]))[0]
    if account_id > -1 and not acc:
        acc = (await get_account_info([account_id]))[0]

    if not acc:
        # Account does not exist -> try create one and get _id
        account_id = (await append_accounts([account_name], save_call=False))[0]
        if account_id > 0:
            return await get_feed(account_name=account_name, account_id=account_id, amount=amount)
        return []

    # Sure: Account exist
    account_data = await MongoDBAsync.account_data.find_one({"_id" : acc["_id"]})
    if not account_data:
        # Account is not analyed --> Make request
        await MongoDBAsync.account_data.insert_one({"_id" : acc["_id"], "analyze" : True})
        return []

    if "feed" not in account_data:
        # No feed --> Make request
        await MongoDBAsync.account_data.update_one({"_id" : acc["_id"]},{"$set" : {"make_feed" : True}})
        return []

    # Get feed and authorperms
    amount = min(len(account_data["feed"]), amount)
    feed_ids = account_data["feed"][:amount]
    authorperms = [] # [{author, permlink}]
    async for post in MongoDBAsync.post_info.find({"_id" : {"$in" : feed_ids}}):
        authorperms.append({"author" : post["author"], "permlink" : post["permlink"]})

    # Do feed request and remove feed items
    await MongoDBAsync.account_data.update_one({"_id" : acc["_id"]},{
                                                "$set" : {"make_feed" : True},
                                                "$pull" : {"feed" : {"$in" : feed_ids}}})
    return authorperms


