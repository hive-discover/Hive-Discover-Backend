import torch as T

T.manual_seed(1)
T.set_printoptions(precision=10, sci_mode=False)
device = T.device("cuda" if T.cuda.is_available() else "cpu")
print("Device available for running: " + device.type)

USER_AGENT = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.0.7) Gecko/2009021910 Firefox/3.0.7'

TEXT_CNN_SAVE_PATH = 'data/TextCNN.v1.pt'
TRAINING_DATASET_PATH = 'data/training_set.json'
TEST_DATASET_PATH = 'data/test_set.json'
WORD_2_VEC_SAVE_PATH = 'data/word2vec.gen'

LEARNING_RATE = 0.001
EMBEDDING_DIM = 400
WINDOW_SIZES = (2, 3, 5)
KERNEL_NUM = 10
CATEGORIES = ['politic', 'technology', 'art', 'animal', 'music', 'travel', 'fashion',
              'gaming', 'purpose', 'food', 'wisdom', 'comedy', 'crypto', 'sports', 'beauty', 'fitness',
              'business', 'lifestyle', 'nature', 'tutorial', 'photography', 'story', 'news']