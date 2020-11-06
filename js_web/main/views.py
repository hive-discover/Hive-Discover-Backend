from django.shortcuts import render
from django.http import JsonResponse, HttpResponse

from datetime import datetime
import sys
sys.path.append("...")
import config
import database


# Create your views here.
def ping(request):
    username = request.GET.get('username', None)
    if username is None:
        # If only the server status is requested
        return render(request, 'ping.js', context={'cmd': 'true'}, content_type="application/x-javascript")

    # Start profiler if needed
    database.commit_query("INSERT INTO tasks(name, timestamp, parameter_one, parameter_two) VALUES (%s, %s, %s, %s);",
                         ("profiler", datetime.utcnow().strftime("%d.%m.%YT%H:%M:%S"), username, ""))
                         
    return render(request, 'ping.js', context={'cmd': 'true'}, content_type="application/x-javascript")



def get_interesting_posts(request):
    username = request.GET.get('username', None)
    if username is None:
        # Error (No Username is given) --> return Error.js
        return render(request, 'error.js', context={"info" : "Please enter a 'username' and use GET"},
                         content_type="application/x-javascript")


    con = config.get_connection()
    posts = database.read_query("SELECT * FROM interesting_posts WHERE username=%s;", (username, ), con=con, close_con=False)
    database.commit_query("INSERT INTO tasks(name, timestamp, parameter_one, parameter_two) VALUES (%s, %s, %s, %s);",
                         ("profiler", datetime.utcnow().strftime("%d.%m.%YT%H:%M:%S"), username, ""), con=con, close_con=False)

    database.commit_query("SET SQL_SAFE_UPDATES = 0;", (), con=con, close_con=False)

    obj = ""
    length = 0
    for _, author, permlink in posts:
        obj += f"{author}/{permlink};"

        database.commit_query("DELETE FROM interesting_posts WHERE username=%s AND author=%s AND permlink=%s;", (username, author, permlink), con=con, close_con=False)

        length += 1
        if length >= 3:
            # Return only 3
            break

    
    
    return render(request, 'get_interesting_posts.js', context={"posts" : obj[:-1]},
                         content_type="application/x-javascript")


def get_post_category(request):
    author = request.GET.get('author', None)
    permlink = request.GET.get('permlink', None)
    if author is None or permlink is None:
        # Error (No author, permlink is given) --> return Error.js
        return render(request, 'error.js', context={"info" : "Please give author, permlink and use GET"},
                         content_type="application/x-javascript")

    result = database.read_query("SELECT * FROM latest_posts WHERE author=%s AND permlink=%s", (author, permlink))
    if len(result) == 0:
        # Error (No post or Connection Error) --> return Error.js
        return render(request, 'error.js', context={"info" : "Cannot find a post or cannot create database connection"},
                         content_type="application/x-javascript")

    author, permlink, category, _ = result[0]
    return render(request, 'get_post_category.js', context={"category" : category},
                         content_type="application/x-javascript")


def get_author_category(request):
    author = request.GET.get('author', None)
    if author is None:
        # Error (No author) --> return Error.js
        return render(request, 'error.js', context={"info" : "Please give author and use GET"},
                         content_type="application/x-javascript")

    result = database.read_query("SELECT * FROM profiler WHERE username=%s;", (author, ))
    if len(result) == 0:
        # Error (No post or Connection Error) --> return Error.js
        return render(request, 'error.js', context={"info" : "Cannot find a profiler"},
                         content_type="application/x-javascript")

    username, category, length, _ = result[0]

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

    return render(request, 'get_author_category.js', context={"category" : [x[0] for x in top_cats], "total": total, "length" : length, "CATEGORIES" : " ".join([config.CATEGORIES[x[1]] for x in top_cats])},
                         content_type="application/x-javascript")

