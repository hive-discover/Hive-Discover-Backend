from database import MongoDB

import argparse
from multiprocessing import Process, Event
import time
from datetime import datetime

# Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-all", "--all", help="start all processes", action="store_true")
parser.add_argument("-api", "--api", help="start api", action="store_true")
parser.add_argument("-f", "--feed", help="start Feed-Making Process", action="store_true")
parser.add_argument("-a", "--analyze", help="start Account Analyzer", action="store_true")
parser.add_argument("-cl", "--chainlistener", help="start Chain Listener Process", action="store_true")
parser.add_argument("-ld", "--langdetector", help="start Lang Detector", action="store_true")
parser.add_argument("-c", "--categorizer", help="start Posts Categorizer", action="store_true")


#   ***  Available methods:
#   (app.start_server, "API Process", True)
#   (feed_making.start, "Feed Maker Process", True)
#   (account_analyzer.start, "Account Analyzer Process", True)
#   (listener.start_listener, "Chain Listener Process", True)
#   (lang_detector.start, "Posts Lang Detector Process", True)
#   (categorizer.start, "Posts Categorizer Process", True)



stop_event = Event()
process_templates = [] # (target, name, daemon)
process_running = [] # Process()


def main():
   # Make template
   args = parser.parse_args()
   if args.api or args.all:
      from api import app
      process_templates.append((app.start_server, "API Process", True))
   if args.feed or args.all:
      from account_tasks import feed_making
      process_templates.append((feed_making.start, "Feed Maker Process", True))
   if args.analyze or args.all:
      from account_tasks import account_analyzer
      process_templates.append((account_analyzer.start, "Account Analyzer Process", True))
   if args.chainlistener or args.all:
      from chain_listener import listener
      process_templates.append((listener.start_listener, "Chain Listener Process", True))
   if args.langdetector or args.all:
      from posts_analyzer import lang_detector
      process_templates.append((lang_detector.start, "Posts Lang Detector Process", True))
   if args.categorizer or args.all:
      from posts_analyzer import categorizer
      process_templates.append((categorizer.start, "Posts Categorizer Process", True))

   # No processes are choosed
   if len(process_templates) == 0:
      print("You do not selected any mode! Please do so...")
      exit(1)

   # More than one process is choosed --> could be harmful
   if len(process_templates) > 1:
      print("It is better to only set on mode. Else if one aborts the other continues and it will not restart")
      print("Anyway, it is starting")
 
   MongoDB.init_global(stats_table=True)
   date = datetime.utcnow()

   # Manage multiple processes
   for target, name, daemon in process_templates:
      job = Process(target=target, name=name, daemon=daemon)
      process_running.append(job)
      job.start()
      MongoDB.stats_table.update_one({"date" : date.strftime("%d.%m.%Y")}, {"$inc" : {f"starting.{date.hour}.{name}" : 1}}, upsert=True)

   # Join process to be inside it
   # If it fails, then Docker restarts it (if one process is only choosed)
   # Two or more processes could result into one failed and one running
   try:
      for job in process_running:
         job.join()
   except KeyboardInterrupt:
      print("Keyboard Interrupt. Closing...")
   
   stop_event.set()
   print("Good bye")


if __name__ == '__main__':
   main()

