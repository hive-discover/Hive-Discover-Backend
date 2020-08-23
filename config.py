import torch as T
from beem import Hive
from beem.blockchain import Blockchain

T.manual_seed(1)
T.set_printoptions(precision=10, sci_mode=False)

HIVE = Hive()
HIVE_NODES = ['https://api.hive.blog', 'https://api.openhive.network', 'https://api.hivekings.com', 'https://anyx.io']

SERVER_PORT = 4156
LAST_ACTIVITY_DELETE = 7 # Minutes

device = T.device("cuda" if T.cuda.is_available() else "cpu")
print("Device available for running: " + device.type)

USER_AGENT = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.0.7) Gecko/2009021910 Firefox/3.0.7'

TEXT_CNN_SAVE_PATH = 'data/TextCNN.v1.pt'
TRAINING_DATASET_PATH = 'data/training_set.json'
TEST_DATASET_PATH = 'data/test_set.json'
WORD_2_VEC_SAVE_PATH = 'data/word2vec.gen'

PROFILER_INTERESTING_FACTOR = 0.95
PROFILER_MINUMUM_DATA_LENGTH = 20

LEARNING_RATE = 0.001
EMBEDDING_DIM = 400
WINDOW_SIZES = (2, 3, 5)
KERNEL_NUM = 10
CATEGORIES = ['politic', 'technology', 'art', 'animal', 'music', 'travel', 'fashion',
              'gaming', 'purpose', 'food', 'wisdom', 'comedy', 'crypto', 'sports', 'beauty', 'fitness',
              'business', 'lifestyle', 'nature', 'tutorial', 'photography', 'story', 'news']


LATEST_POSTS = [] # (permlink, author, category, date)

                        
