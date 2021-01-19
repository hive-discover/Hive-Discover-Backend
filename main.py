from flask_server import start_server
from agents import *
from config import *
from network import TextCNN, LangDetector
from hive import AccountsManager, PostsManager

from threading import Thread
import time

from gensim.models import word2vec, KeyedVectors

def handle_task(task : dict, running_tasks : list):
   '''Do the job'''

   if task["job"] == "make_feed":
      profiler = Profiler(task["username"])
      profiler.make_feed()

   # Release
   running_tasks.remove(task)

def task_manager():
   '''Manage all incoming tasks'''

   running_tasks = []
   while 1:
      if len(statics.OPEN_TASKS) == 0 or len(running_tasks) > MAX_RUNNING_TASKS:
         # Nothing to do
         time.sleep(0.1)
         continue

      # something to do --> get first and pop it
      task = statics.OPEN_TASKS[0]
      statics.OPEN_TASKS.pop(0)

      if task in running_tasks:
         # Already running
         continue
      
      # TODO: Implement rules (optionally)
      
      # Start the job
      running_tasks.append(task)
      t = Thread(target=handle_task, args=(task, running_tasks), daemon=True, name=f"Do Task - {len(running_tasks)}")
      t.start()




def init():
   '''Load all data'''

   # 1. Load Word-2-Vec / Fastteext Model
   print("", end=f"\r Load:   Fasttext: ...")
   statics.FASTTEXT_MODEL = KeyedVectors.load(FASTTEXT_MODEL_PATH)
  # statics.WORD2VEC_MODEL = word2vec.Word2Vec.load(WORD2VEC_MODEL_PATH)
   
   # 2. Load Fasttext Lang Detector
   print("", end=f"\r Load:   Word2Vec: OK  Lang-Detector: ...")
   statics.LANG_DETECTOR = LangDetector(load_model=True)

   # 3. Load TextCNN Model
   print("", end=f"\r Load:   Word2Vec: OK   Lang-Detector: OK   TextCNN: ...")
   statics.TEXTCNN_MODEL, from_disc = TextCNN.load_model()

   print("", end=f"\r Load:   Word2Vec: OK   TextCNN: OK   ")
   if not from_disc:
      print("", end=f"\r Load:   Word2Vec: OK   Lang-Detector: OK   TextCNN: OK (created new one)")

   statics.LEMMATIZER = Lemmatizer()

   
def main():
   # Start Flask Server
   t = Thread(target=start_server, daemon=True, name="Flask Server - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # Posts Manager
   statics.POSTS_MANAGER = PostsManager()
   t = Thread(target=statics.POSTS_MANAGER.get_latest_posts, daemon=True, name="Posts Manager - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # Post Searcher - Create Indexer
   statics.POST_SEARCH_AGENT = PostSearcher()
   t = Thread(target=statics.POST_SEARCH_AGENT.create_search_index, daemon=True, name="Search Indexer - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # Post Categories - Create Indexer
   statics.POSTS_CATEGORY = PostsCategory()
   t = Thread(target=statics.POSTS_CATEGORY.create_search_index, daemon=True, name="Category Indexer - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # Account Manager - 
   statics.ACCOUNTS_MANAGER = AccountsManager()
   t = Thread(target=statics.ACCOUNTS_MANAGER.run, daemon=True, name="Accounts Manager - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   # Account Search - Create Indexer
   statics.ACCOUNTS_SEARCHER = AccountSearch()
   t = Thread(target=statics.ACCOUNTS_SEARCHER.create_search_index, daemon=True, name="Accounts Indexer - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)


   # Task Manager
   t = Thread(target=task_manager, daemon=True, name="Task Manager - Thread")
   t.start()
   statics.THREADS_RUNNING.append(t)

   while 1:
      time.sleep(1)


if __name__ == '__main__':
   init()
   main()
