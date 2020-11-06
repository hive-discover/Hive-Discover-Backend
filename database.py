import mysql
import time
import config


def commit_query(query, values, con = None, close_con = True):
    # delete : SET SQL_SAFE_UPDATES = 0;
    if con is None:
        con = config.get_connection()
        if con is None:
            # Error occured
            return -1

    cursor = con.cursor()
    cursor.execute(query, values)
    con.commit()

    if close_con:
        con.close()

    return cursor.rowcount

def read_query(query, values, con = None, close_con = True):
    if con is None:
        con = config.get_connection()
        if con is None:
            # Error occured
            return []

    cursor = con.cursor()
    cursor.execute(query, values)
    results = cursor.fetchall()

    if close_con:
        con.close()
    return results

# Background thread
def latest_post_count_manager():
    con = config.get_connection()
    cursor = con.cursor()
    while 1:            
        cursor.execute("SELECT COUNT(*) FROM latest_posts")
        result = cursor.fetchall() # return [(COUNT,)]

        if len(result) == 0:
            # Error occured
            print("[WARNING] Error while trying to get count of latest_posts")
            time.sleep(20)
            continue

        # uppdate statics.count
        count = result[0][0]
        config.statics.LATEST_POSTS_START_LIMIT = count

        # wait
        time.sleep(30)

       
