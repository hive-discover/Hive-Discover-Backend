import torch as T
from beem.nodelist import NodeList

class statics():
    Profilers = []
    LatestPosts = [] # (author, permlink, interesting_profile, timestamp)
    WordEmbedding = None
    TextCNN = None


HOST_IP = '192.168.178.20'
WEBSOCKET_PORT = 1568


device = T.device("cuda" if T.cuda.is_available() else "cpu")
print("Device available for running: " + device.type)

HIVE_NODES = NodeList().get_hive_nodes()


WORD2VEC_PATH = 'data/word2vec.gen'
TEXTCNN_PATH = 'data/TextCNN.pt'


LEARNING_RATE = 0.00001
EMBEDDING_DIM = 400
WINDOW_SIZES = (2, 3, 5)
KERNEL_NUM = 10
INTERESTING_FACTOR = 0.95


USER_AGENT = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.0.7) Gecko/2009021910 Firefox/3.0.7'


CATEGORIES = ['politic', 'technology', 'art', 'animal', 'music', 'travel', 'fashion',
              'gaming', 'purpose', 'food', 'wisdom', 'comedy', 'crypto', 'sports', 'beauty', 'fitness',
              'business', 'lifestyle', 'nature', 'tutorial', 'photography', 'story', 'news', 'health',
              'coding', 'education', 'introduceyourself', 'science', 'film', 'challenge', 'gardening', 'hive',
              'history', 'society', 'economic', 'thoughts', 'future', 'blockchain', 'psychology', 'family',
              'finance', 'work', 'philosophy', 'culture', 'trading', 'motivation', 'statistics']

