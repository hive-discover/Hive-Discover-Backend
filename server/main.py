from network import *
import hive

from threading import Thread
import time
from inspect import getsourcefile
import os.path as path, sys
current_dir = path.dirname(path.abspath(getsourcefile(lambda:0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])

# Modules from parent Directory
import config  
import database
sys.path.pop(0)



def task_manager():
    con = config.get_connection()
    while 1:
        # Update analytics
        database.commit_query("UPDATE analytics SET value_one=%s WHERE name=%s", 
                                (len(config.statics.task_list), "tasks_running"), con=con, close_con=False)

        while len(config.statics.task_list) >= config.MAX_TASK_THREADS:
            # Thread limit is reached --> Wait for completing
            time.sleep(0.5)

        # Get first available task
        tasks = database.read_query("SELECT * FROM tasks LIMIT 1;", (), con=con, close_con=False)

        if len(tasks) == 0:
            # If nothing is to do
            time.sleep(0.5)
            continue

        # Get first element and test if it is running
        name, timestamp, p_one, p_two = tasks[0]
        already_running = False
        for _name, _, _p_one, _p_two in config.statics.task_list:
            if name in _name and p_one in _p_one and p_two in _p_two:
                # already running
                already_running = True
                break

        # Delete element
        database.commit_query("SET SQL_SAFE_UPDATES = 0;", (), con=con, close_con=False)
        database.commit_query("DELETE FROM tasks WHERE name=%s AND parameter_one=%s AND parameter_two=%s;",
                                 (name, p_one, p_two), con=con, close_con=False)

        if already_running:
            # abort
            continue

        # Insert in list and Run
        config.statics.task_list.append(tasks[0])
        def run(task):
            name, timestamp, p_one, p_two = task

            if 'profiler' in name:
                p = Profiler(p_one, start_get_post_thread=False)
                p.find_interestings()

            if 'adjust' in name:
                p = Profiler(p_one, start_get_post_thread=False)
                p.adjust(categories_as_strings=p_two.split(','))
            
            if 'set_to_zero' in name:
                p = Profiler(p_one, start_get_post_thread=False)
                p.set_zero(category=p_two)  

            if 'delete_user' in name:
                database.commit_query("DELETE FROM profiler WHERE username=%s;",
                                 (p_one, ))  
                database.commit_query("DELETE FROM interesting_posts WHERE username=%s;",
                                 (p_one, ))           
                

            # delete task
            config.statics.task_list.remove(task)

        # Start thread
        t = Thread(target=run, args=(tasks[0], ))
        t.name = f"T - {name} ({str(p_one)};{str(p_two)})"
        t.daemon = True
        t.start()
        

def reset_analytics():
    con = config.get_connection()

    # Delete all
    database.commit_query("SET SQL_SAFE_UPDATES = 0;", (), con=con, close_con=False)
    database.commit_query("DELETE FROM analytics", (), con=con, close_con=False)

    # tasks_running (currently)
    database.commit_query("INSERT INTO analytics(name, value_one, value_two, value_three) VALUES (%s, %s, %s, %s)",
                             ("tasks_running", 0, None, None), con=con, close_con=False)
    
    # connections (per second)
    database.commit_query("INSERT INTO analytics(name, value_one, value_two, value_three) VALUES (%s, %s, %s, %s)",
                             ("connections", 0, None, None), con=con, close_con=False)

    # requests (per second)
    database.commit_query("INSERT INTO analytics(name, value_one, value_two, value_three) VALUES (%s, %s, %s, %s)",
                             ("requests", 0, None, None), con=con, close_con=False)

    con.close()
    print("[INFO] Analysing is running")

#   --- STARTER --- 

def main():
    # Init
    config.init_server()
    hive.LatestPostManager()
    reset_analytics()


    # Start counter thread
    post_count_thread = Thread(target=database.latest_post_count_manager) 
    post_count_thread.name = "Get latest_posts count"
    post_count_thread.daemon = True
    post_count_thread.start()

    # Start task manager thread
    task_manager_thread = Thread(target=task_manager) 
    task_manager_thread.name = "Taskmanager"
    task_manager_thread.daemon = True
    task_manager_thread.start()

    # Start remove Profiler thread
    remove_old_profiler_thread = Thread(target=Profiler.remove_old_profiler) 
    remove_old_profiler_thread.name = "Remove old Profiler"
    remove_old_profiler_thread.daemon = True
    #remove_old_profiler_thread.start()
         
    # Wait until something happens
    while True:
        try:
            _input = input()

            if 'exit' in _input or 'break' in _input or 'quit' in _input:
                # Stop
                break
            if 'tasks' in _input:
                # Get all tasks
                print(f"Tasks({len(config.statics.task_list)}) are running: ")
                for name, timestamp, _, _ in config.statics.task_list:
                    print(f"{name} from {timestamp}")
            if 'profiler' in _input:
                # Profile one --> Add task
                username = _input.split(' ')[1] #profiler christopher2002
                database.commit_query("INSERT INTO tasks(name, timestamp, parameter_one, parameter_two) VALUES (%s, %s, %s, %s);",
                         ("profiler", datetime.utcnow().strftime("%d.%m.%YT%H:%M:%S"), username, ""))
                print("Created profiling task for " + username)


        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()