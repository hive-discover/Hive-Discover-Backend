from multi_agents import *
from config import *
from flask_server import app

from threading import Thread
from multiprocessing import Process, Event, Queue
import time

stop_event = Event()
account_manager_queue = Queue()
stats_manager_queue = Queue()

def old_main():
   '''Start all'''
   # Setup all statics
   statics.STATISTIC_AGENT = Statistics()
   statics.POSTS_MANAGER = PostsManager()
   statics.POSTS_CATEGORY = PostsCategory()
   statics.LEMMATIZER = Lemmatizer()
   statics.ACCOUNTS_MANAGER = AccountsManager()
   statics.ACCOUNTS_SEARCHER = AccountSearch()
   statics.ACCESS_TOKEN_MANAGER = AccessTokenManager()

   # 1. Start Flask Server
   t = Thread(target=start_server, daemon=True, name="Flask Server - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)
   
   # 2. Statistics Manager 
   t = Thread(target=statics.STATISTIC_AGENT.run, daemon=True, name="Statistics - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # 3. Post Categories - Create Indexer  
   t = Thread(target=statics.POSTS_CATEGORY.create_search_index, daemon=True, name="Category Indexer - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # 4. Posts Categoroy - Anti Plagialism
   t = Thread(target=statics.POSTS_CATEGORY.anti_plagiarlism, daemon=True, name="Anti Plagialism - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # 5. Account Manager - Runner 
   t = Thread(target=statics.ACCOUNTS_MANAGER.run, daemon=True, name="Accounts Manager - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # 6. Account Search - Create Index
   t = Thread(target=statics.ACCOUNTS_SEARCHER.create_search_index, daemon=True, name="Account Indexer - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # 7. Chain Listener
   t = Thread(target=listen_to_blockchain, daemon=True, name="Chain Listener - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # 8. Access Token Manager 
   t = Thread(target=statics.ACCESS_TOKEN_MANAGER.run, daemon=True, name="AccessToken Manager - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # 9. Load Files
   #load_data()

   while 1:
      time.sleep(1)

def main():
   mp_posts = MP_PostsAnalyse(stop_event)
   mp_chain_listener = MP_ChainListener(stop_event)
   mp_account_manager = MP_AccountManager(stop_event, account_manager_queue)
   mp_api_handler = MP_APIHandler(stop_event, account_manager_queue, stats_manager_queue)
   mp_stats_handler = MP_StatsManager(stop_event, stats_manager_queue)

   #mp_posts.start()
   mp_chain_listener.start()
   #mp_account_manager.start()
   mp_api_handler.start()
   #mp_stats_handler.start()

   # MainThread
   while 1:
      _input = input()
      if "exit" in _input or "break" in _input:
         break

   stop_event.set()
   #mp_posts.join(timeout=10)
   mp_chain_listener.join(timeout=10)
   #mp_account_manager.join(timeout=10)
   mp_api_handler.join(timeout=10)
   #mp_stats_handler.join(timeout=10)


if __name__ == '__main__':
   main()

