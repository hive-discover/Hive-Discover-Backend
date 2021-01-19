from pymongo.common import validate_positive_float
from agents import *
from config import *

from flask_cors.core import RegexObject
from flask import Flask, jsonify, request
from flask_cors import CORS

import pymongo
from pymongo import MongoClient

import requests
from threading import Thread

app = Flask(__name__)
CORS(app)


@app.route('/')
def index():
    '''Shows that it is alive'''
    return 'Service is running'

@app.route('/search-post', methods=["GET"])
def search_post():
    query = request.args.get("q")
    if query is None:
        return jsonify({"status" : "failed", "info" : "no query were given"}), 400

    max = 30
    if request.args.get("max"):
        max = int(request.args.get("max"))

    get_hive_posts = False
    if request.args.get("data") and request.args.get("data") == "true":
        get_hive_posts = True

    response = {"status" : "ok", "posts" : [], "seconds" : 0, "records" : 0}

    # Get Search results and get author and permlink from post_id
    search_results = statics.POST_SEARCH_AGENT.search(query, k=max)
    response["seconds"] = search_results["seconds"]
    response["records"] = search_results["records"]

    # Database Conenction
    mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
    post_table = mongo_client[DATABASE_NAME].posts

    worker = []
    for result in search_results["results"]:
        post_data = post_table.find_one({"post_id" : result["post_id"]})

        if post_data:
            if get_hive_posts:
                def get(author, permlink):
                    p = Comment(f'@{author}/{permlink}')
                    response["posts"] = list(response["posts"]) + [{"a" : p["author"], "p" : p["permlink"], "body" : p["body"], "title" : p["title"], "json_metadata" : p["json_metadata"], "tags" : p["tags"]}]
                t = Thread(target=get, args=(post_data["author"], post_data["permlink"]), daemon=True)
                t.start()
                worker.append(t)
            else:
                response["posts"] = list(response["posts"]) + [{"a" : post_data["author"], "p" : post_data["permlink"]}]

    # wait to finish
    for t in worker:
        t.join(timeout=5)

    return jsonify(response), 200

@app.route('/search-account', methods=["GET"])
def search_account():
    '''Searches for an account'''
    query = request.args.get("q")
    if query is None:
        return jsonify({"status" : "failed", "info" : "no query were given"}), 400

    # Get Search results and return
    search_results = statics.ACCOUNTS_SEARCHER.search(query)
    return {"status" : "ok", "accounts" : search_results["results"], "seconds" : search_results["seconds"], "records" : search_results["records"]}, 200

@app.route('/get-feed', methods=["GET"])
def get_feed():
    username = request.args.get("username")
    if username is None:
        return jsonify({"status" : "failed", "info" : "no username were given"}), 400

    get_hive_posts = False
    if request.args.get("data") and request.args.get("data") == "true":
        get_hive_posts = True

    return statics.ACCOUNTS_MANAGER.get_feed(username, hive_posts=get_hive_posts), 200

@app.route('/get-profiler', methods=["GET"])
def get_profiler():
    username = request.args.get("username")
    if username is None:
        return jsonify({"status" : "failed", "info" : "no username were given"}), 400

    profiler = Profiler(username, start_analyse_when_create=False)
    p_dict = dict(profiler.profiler)
    return_dict = {"loading" : p_dict["loading"], "last_analyze" : p_dict["last_analyze"]}

    if not p_dict["categories"] is None:
        # Combine categories with index of topics and order then
        p_dict["categories"] = [(value, index) for index, value in enumerate(p_dict["categories"])]
        p_dict["categories"] = sorted(p_dict["categories"], key=lambda x: x[0], reverse=True)

        # Only let top 12 together and add topic
        cats = []
        rest = 0
        for index, (value, topic_index) in enumerate(p_dict["categories"]):
            if index < 12:
                cats.append({"value" : value, "topic" : CATEGORIES[topic_index][0]})
            else:
                rest += value

        return_dict["categories"] = cats

    return jsonify(return_dict)
    


def start_server():
    app.run()

if __name__ == '__main__':
    start_server()