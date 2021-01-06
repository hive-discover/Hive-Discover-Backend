from pymongo.common import validate_positive_float
from agents import *
from config import *

from flask_cors.core import RegexObject
from flask import Flask, jsonify, request
from flask_cors import CORS

import pymongo
from pymongo import MongoClient

from threading import Thread

app = Flask(__name__)
CORS(app)


@app.route('/')
def index():
    '''Shows that it is alive'''
    return 'Service is running'

@app.route('/search', methods=["GET"])
def search():
    query = request.args.get("q")
    if query is None:
        return jsonify({"status" : "failed", "info" : "no query were given"}), 400

    response = {"status" : "ok", "results" : [], "seconds" : 0, "records" : 0}

    # Get Search results and get author and permlink from post_id
    search_results = statics.POST_SEARCH_AGENT.search(query)
    response["seconds"] = search_results["seconds"]
    response["records"] = search_results["records"]

    # Database Conenction
    mongo_client = MongoClient(DATABASE_HOST, DATABASE_PORT)
    post_table = mongo_client[DATABASE_NAME].posts

    for result in search_results["results"]:
        post_data = post_table.find_one({"post_id" : result["post_id"]})

        if post_data:
            response["results"] = list(response["results"]) + [
                {"author" : post_data["author"], "permlink" : post_data["permlink"], "score" : result["score"]}]

    return jsonify(response), 200

@app.route('/get-feed', methods=["GET"])
def get_feed():
    username = request.args.get("username")
    if username is None:
        return jsonify({"status" : "failed", "info" : "no username were given"}), 400

    profiler = Profiler(username, start_analyse_when_create=False)

    # Start a making feed job
    statics.OPEN_TASKS.append({
        "job" : "make_feed",
        "username" : username
    })

    # Return proceed feed
    return profiler.get_feed(), 200


    
def start_server():
    app.run()

if __name__ == '__main__':
    start_server()