import numpy as np


LEARNING_RATE = 0.000001
EMBEDDING_DIM = 400
WINDOW_SIZES = (2, 3, 5)
KERNEL_NUM = 10
INTERESTING_FACTOR = 0.95

class statics:
    task_list = []
    Word2Vec = None
    TextCNN = None
    LATEST_POSTS_START_LIMIT = 0

def init_server():    
    from gensim.models import word2vec
    statics.Word2Vec = word2vec.Word2Vec.load('server/data/word2vec.gen')
    print("[INFO] Loaded pretrained Word2Vec model.")

    from network import TextCNN
    statics.TextCNN = TextCNN.load_model('server/data/TextCNN.pt')
    print("[INFO] Loaded pretrained TextCNN model.")


import mysql.connector 
def get_connection():
    try:
        return mysql.connector.connect(
                host="192.168.178.14",
                port=3306,
                database="hive-discover",
                user="test",
                password="test123")
    except mysql.connector.errors.InterfaceError:
        print("[FAILED] Can't connect to the database!")
        return None


MAX_TASK_THREADS = 20
PROFILER_MIN_DATA = 2 # 15
PROFILER_MAX_DATA = 100 # 100
PROFILER_DELETE_TIME = 12 # in Hours (Half day is like the full day --> they sleep and does not come back)
INTERESTING_FACTOR = 0.175
MAX_INTERSTING_POSTS = 7


CATEGORIES = ['politic', 'technology', 'art', 'animal', 'music', 'travel', 'fashion', 'gaming', 'purpose',
              'food', 'meat', 'vegetarian', 'vegan', 'recipe', 'wisdom', 'comedy', 'crypto', 'sports', 'training',
              'football', 'soccer', 'tennis', 'golf', 'yoga', 'beauty', 'fitness', 'business', 'lifestyle', 'nature',
              'tutorial', 'diy', 'photography', 'story', 'news', 'covid-19', 'health', 'coding', 'computer', 
              'education', 'biology', 'introduceyourself', 'science', 'film', 'challenge', 'gardening', 'hive', 
              'history', 'society', 'media', 'market', 'economic', 'thoughts', 'future', 'blockchain', 'psychology',
              'family', 'finance', 'work', 'philosophy', 'culture', 'trading', 'motivation', 'statistics', 'development',
              'mechanic', 'physics']