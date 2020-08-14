import config as conf
from agent import *
from helper import *
import network

import time
import re

def main():
    #embedding = network.WordEmbedding()
    #embedding.train_model_dataset()

    model = network.load_model()
    #model = Trainer(model).train(100, retrain_word2vec=False)
    Tester(model).run()
    

if __name__ == "__main__":
    start = time.time()
    main()

    end = time.time()
    print(f"Program took {end - start}s")
    print("   ---   Goodbye   ---")

