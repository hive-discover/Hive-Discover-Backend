from flask import Flask, jsonify, request
from flask_cors import CORS

from datetime import datetime

from inspect import getsourcefile
import os.path as path, sys
current_dir = path.dirname(path.abspath(getsourcefile(lambda:0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])

# Modules from parent Directory
import config  
import database
sys.path.pop(0)

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    ''' Index site --> Show if everything is good '''
    return 'Service is running'

@app.route('/ping', methods=['GET', 'POST'])
def ping():
    ''' AJAX Call for ping: Test the connection and maybe start a profiler '''
    username = request.args.get('username', None, type=str)
    if username:
        database.commit_query("INSERT INTO tasks(name, timestamp, parameter_one, parameter_two) VALUES (%s, %s, %s, %s);",
                         ("profiler", datetime.utcnow().strftime("%d.%m.%YT%H:%M:%S"), username, ""))
     
    return jsonify({"status" : "succes"})

@app.route('/get_interesting_posts', methods=['GET', 'POST'])
def get_interesting_posts():
    ''' Ajax Call: get 3 interesting posts '''
    username = request.args.get('username', None, type=str)
    if username is None:
        # Return error json, if no username is given
        return jsonify({"status" : "failed", "code" : 1, "message" : "No username is given"})

    # Get 3 posts
    LIMIT = 3
    con = config.get_connection()
    posts = database.read_query("SELECT * FROM interesting_posts WHERE username=%s LIMIT %s;", (username, LIMIT),
                                con=con, close_con=False)

    # Prepare and Delete them
    database.commit_query("SET SQL_SAFE_UPDATES = 0;", (), con=con, close_con=False)
    for index, (_, author, permlink) in enumerate(posts):
        posts[index] = { "author" : author, "permlink" : permlink }

        database.commit_query("DELETE FROM interesting_posts WHERE username=%s AND author=%s AND permlink=%s;",
                             (username, author, permlink), con=con, close_con=False)

    # Start profiler
    database.commit_query("INSERT INTO tasks(name, timestamp, parameter_one, parameter_two) VALUES (%s, %s, %s, %s);",
                         ("profiler", datetime.utcnow().strftime("%d.%m.%YT%H:%M:%S"), username, ""), con=con, close_con=False)

    if len(posts) == 0:
        return jsonify({"status" : "failed", "code" : 1, "msg" : "No posts currently available"})

    return jsonify({"status" : "succes", "posts" : posts})

@app.route('/get_user_profile', methods=['GET', 'POST'])
def get_user_profile():
    ''' AJAX CALL: Get user data'''
    username = request.args.get('username', None, type=str)
    if username is None:
        # Error (No username)
        return jsonify({ "status" : "failed", "code" : 1,  "msg" : "No username is given"})

    result = database.read_query("SELECT * FROM profiler WHERE username=%s;", (username, ))
    if len(result) == 0:
        # Error (No post or Connection Error) --> return Error.js
        return jsonify({ "status" : "failed", "code" : 2, "msg" : "Username is unknown"})

    username, category, length, _, finished = result[0]

    # get total value
    cat = category.split(' ') 
    total = 0
    for c in cat:
        total += float(c)

    # get top 10 profiler categories
    top_cats = []         
    while len(top_cats) < 10:
        highest = (0, -1) # (value, cat_index)
        for index, x in enumerate(cat):
            if highest[1] == -1 or float(x) > highest[0]:
                # first or better
                highest = (float(x), index)

        top_cats.append(highest)
        cat[highest[1]] = 0

    return jsonify({"status" : "succes", "top_cats" : [{ "value" : x[0], "label" : config.CATEGORIES[x[1]]} for x in top_cats],
                     "total": total, "data_length" : length, "finished" : "1" in finished})

@app.route('/adjust', methods=['GET', 'POST'])
def adjust():
    ''' AJAX CALL: Adjust user'''
    username = request.args.get('username', None, type=str)
    cats = request.args.get('cats', None, type=str)
    if username is None or cats is None:
        # Error (No username, cats is given) --> return Error.js
        return jsonify({"status" : "failed", "code" : 7, "msg" : "No username/categories are given"})

    # Enter in tasks
    database.commit_query("INSERT INTO tasks(name, timestamp, parameter_one, parameter_two) VALUES (%s, %s, %s, %s);",
                         ("adjust", datetime.utcnow().strftime("%d.%m.%YT%H:%M:%S"), username, cats))

    return jsonify({ "status" : "succes"})

@app.route('/set_to_zero', methods=['GET', 'POST'])
def set_to_zero():
    ''' AJAX CALL: Set category for user to zero'''
    username = request.args.get('username', None, type=str)
    cat = request.args.get('cat', None, type=str)
    if username is None or cat is None:
        # Error (No username, cats is given) --> return Error.js
        return jsonify({"status" : "failed", "code" : 7, "msg" : "No username/category is given."})

    # Enter in tasks
    database.commit_query("INSERT INTO tasks(name, timestamp, parameter_one, parameter_two) VALUES (%s, %s, %s, %s);",
                         ("set_to_zero", datetime.utcnow().strftime("%d.%m.%YT%H:%M:%S"), username, cat))

    return jsonify({"status" : "succes"})

@app.route('/delete_user', methods=['GET', 'POST'])
def delete_user():
    ''' AJAX CALL: delete user'''
    username = request.args.get('username', None, type=str)
    if username is None:
        # Error (No username is given)
        return jsonify({"status" : "failed", "code" : 3, "msg" : "No username is given."})

    # Enter in tasks
    database.commit_query("INSERT INTO tasks(name, timestamp, parameter_one, parameter_two) VALUES (%s, %s, %s, %s);",
                         ("delete_user", datetime.utcnow().strftime("%d.%m.%YT%H:%M:%S"), username, ""))

    return jsonify({"status" : "succes"})

@app.route('/get_categories', methods=['GET', 'POST'])
def get_categories():
    ''' AJAX CALL: Get all categories'''
    return jsonify({"status" : "succes", "list" : [x for x in config.CATEGORIES]})

@app.route('/get_analytics', methods=['GET', 'POST'])
def get_analytics():
    ''' AJAX CALL: get analytics'''
    con = config.get_connection()
    context = {}

    # Get tasks_running
    element = database.read_query("SELECT value_one FROM analytics WHERE name=%s;", ("tasks_running", ), con=con, close_con=False)[0] # [(value, )]
    context["tasks_running"] = int(element[0])
    context["status"] = "succes"
    
    return jsonify(context)

if __name__ == "__main__":
    # Start
    app.run()
