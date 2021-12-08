from database import MongoDB

import argparse
from multiprocessing import Process, Event
from datetime import datetime

# Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-all", "--all", help="start all processes", action="store_true")
parser.add_argument("-ld", "--langdetector", help="start Lang Detector", action="store_true")
parser.add_argument("-c", "--categorizer", help="start Posts Categorizer", action="store_true")
parser.add_argument("-b", "--bot", help="start Bot", action="store_true")
parser.add_argument("-tm", "--test_modules", help="Test dependencies by importing all modules", action="store_true")


#   ***  Available methods:
#   (lang_detector.start, "Posts Lang Detector Process", True)
#   (categorizer.start, "Posts Categorizer Process", True)
#   (bot.start, "Bot Process", True)



stop_event = Event()
process_templates = [] # (target, name, daemon)
process_running = [] # Process()


def main():
   # Make template
   args = parser.parse_args()
   if args.test_modules or args.all:
      print("Importing all modules...")
      from posts_analyzer import lang_detector
      from posts_analyzer import async_categorizer
      from bot import ac_bot
      print("All modules were imported successfully.")
   if args.langdetector or args.all:
      from posts_analyzer import lang_detector
      process_templates.append((lang_detector.start, "Posts Lang Detector Process", True))
   if args.categorizer or args.all:
      from posts_analyzer import async_categorizer
      process_templates.append((async_categorizer.start, "Posts Categorizer Process", True))
   if args.bot or args.all:
      from bot import ac_bot
      process_templates.append((ac_bot.start, "Bot Process", True))

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
   exit(1)


if __name__ == '__main__':
   main()

