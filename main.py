import config as conf
from agent import *
from helper import *
import network
import server

import argparse
import time
import re, csv

parser = argparse.ArgumentParser()
parser.add_argument('-train', '--train', help='Train the text - and word2vec network. Epochs must be given')
parser.add_argument('-test', '--test', help='Test some posts', action='store_true')
parser.add_argument('-discover', '--discover', help='Get posts to discover for a user. Username has to be given')
parser.add_argument('-production', '--production', help='Start the production mode. Posts were categorized and server is running', action='store_true')

args = parser.parse_args()

def main():
    # Load both networks
    embedding = network.WordEmbedding()
    model = network.load_model()

    if args.train:       
        model = Trainer(model, embedding).train(int(args.train), retrain_word2vec=True)
    if args.test:
        Tester(model, embedding).run()

    # ---   USAGE   ---

    if args.production:
        # Start get latest post manager        
        LatestPostsManager(model, embedding)
        
        server.init(model, embedding)
        server.start_listener()

        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                if 'y' in input('DO YOU WANT TO QUIT? Y/N').lower():
                    break

    if args.discover:
        LatestPostsManager(model, embedding)
        advisor = DiscoverAdvisor(str(args.discover).lower(), model, embedding)
        while len(advisor.interesting_posts) < 3:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break

        print(f'Got {len(advisor.interesting_posts)} interesting posts:')
        for post in advisor.interesting_posts:
            print(post)    
    

if __name__ == "__main__":
    start = time.time()
    main()

    end = time.time()
    print(f"Program took {end - start}s")
    print("   ---   Goodbye   ---")

