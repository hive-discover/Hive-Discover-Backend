import network
import config as conf
import helper
import server
import hive

import time

# Load statics
conf.statics.WordEmbedding = network.WordEmbedding()
conf.statics.TextCNN = network.TextCNN().load_model()

#conf.statics.TextCNN = network.Trainer(model=conf.statics.TextCNN, embedding=conf.statics.WordEmbedding, train_word2vec=True).train(30)
conf.statics.TextCNN = network.Trainer(model=conf.statics.TextCNN, embedding=conf.statics.WordEmbedding, train_word2vec=False).train_alone()


#profiler = network.Profiler('christopher2002')

# start Server
#server.WebSocketServer()
#hive.LatestPostManager()

#while True:
    #time.sleep(1)