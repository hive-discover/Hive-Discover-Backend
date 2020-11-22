from inspect import getsourcefile
import os.path as path, sys
current_dir = path.dirname(path.abspath(getsourcefile(lambda:0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])

# Modules from parent Directory
import config  
import database
sys.path.pop(0)

import time

REMOTE_ADDRS = []

# Connection: count of all current Requests with the SAME IP --> remove douples: list(dict.fromkeys(REMOTE_ADDRS)) and len()
# Requests: count of all current Requests --> len(REMOTE_ADDRS)

def run():
    con = config.get_connection()
    while 1:
        start_time = time.time()
        request_count = len(REMOTE_ADDRS)
        connection_count = len(list(dict.fromkeys(REMOTE_ADDRS)))
        REMOTE_ADDRS.clear()


        # Update
        database.commit_query("UPDATE analytics SET value_one=%s WHERE name=%s", 
                                (request_count, "requests"), con=con, close_con=False)
        database.commit_query("UPDATE analytics SET value_one=%s WHERE name=%s", 
                                (connection_count, "connections"), con=con, close_con=False)

        # wait a second (exactly)        
        time.sleep((1000 - (time.time() - start_time)) / 1000)

        