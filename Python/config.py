HOST_IP = "0.0.0.0"
HOST_PORT = 888

WORD2VEC_MODEL_PATH = "data/word2vec.gen"
FASTTEXT_MODEL_PATH = "data/fasttext/fasttext_gensim.model"
TEXTCNN_MODEL_PATH = "data/TextCNN_Model_7.pt" 
LANG_FASTTEXT_MODEL = "data/fasttext-lang.ftz"
FAKENEWSCNN_MODEL_PATH = "data/FakeNewsCNN.pt"

MIN_KNOWN_WORDS = 8

MAX_SEARCH_INDEX_DELTA = 60 * 60 # in seconds = 1 hour

# Database (MongoDB)
import os
if os.environ.get("MongoDB_Host", None) == None:
    # Env's not set --> load from .env file
    from dotenv import load_dotenv, find_dotenv
    from pathlib import Path
    env_file = find_dotenv(Path("Python/docker_variables.env"))
    load_dotenv(env_file, verbose=True)
    print(f"Loaded ENV-Variables from: {env_file}")
    del env_file

DATABASE_HOST = os.environ.get("MongoDB_Host", None)
DATABASE_PORT = int(os.environ.get("MongoDB_Port", 27017))
DATABASE_NAME = os.environ.get("MongoDB_Name", None)
DATABASE_USER = os.environ.get("MongoDB_User", None)
DATABASE_PASSWORD = os.environ.get("MongoDB_Password", None)

FEED_API_PORT = int(os.environ.get("NMSLIB_API_Port", -1))
WORDVEC_API_PORT = os.environ.get("WordVecApi_Port", 7879)
AMABLE_DB_Port = os.environ.get("AmableDB_Port", 3399)

print(DATABASE_HOST, DATABASE_NAME, DATABASE_USER)

# Ac-Bot
AC_BOT_POSTING_WIF = os.environ.get("AC_BOT_POSTING_WIF", None)
AC_BOT_VOTE_COUNT = 25

# Profiler
ACCOUNT_MAX_VOTES = 1000
ACCOUNT_MAX_POSTS = 1000
ACCOUNT_MAX_FEED_LEN = 30
ACCOUNT_MIN_FEED_LEN = 100

# Tasks
MAX_RUNNING_TASKS = 20

FREQUENZY_CHARACTERS = [c for c in "abcdefghijklmnopqrstuvwxyz.-_0123456789"]

class statics:
    OPEN_TASKS = []
    THREADS_RUNNING = []
    
    POSTS_CATEGORY = None # agents.PostsCategory
    POSTS_MANAGER = None # hive.PostsManager
    ACCOUNTS_MANAGER = None # hive.AccountsManager
    ACCOUNTS_SEARCHER = None # agents.AccountsSearcher
    LANG_DETECTOR = None # network.LangDetector
    ACCESS_TOKEN_MANAGER = None # agents.AccessTokenManager

    WORD2VEC_MODEL = None
    FASTTEXT_MODEL = None # KeyedVectors
    TEXTCNN_MODEL = None 
    LEMMATIZER = None

    STATISTIC_AGENT = None # agents.Statistics




CATEGORIES = [['politic', 'politics', 'election'], ['technology', 'tech', 'technical', 'blockchain'], ['art', 'painting', 'drawing', 'sketch'], ['animal', 'pet'], ['music'],
            ['travel'], ['fashion', 'style', 'mode', 'clothes'], ['gaming', 'game', 'splinterlands'], ['purpose'],
            ['food', 'eat', 'meat', 'vegetarian', 'vegetable', 'vegan', 'recipe'], ['wisdom'], ['comedy', 'funny', 'joke'],
            ['crypto'], ['sports', 'sport', 'training', 'train', 'football', 'soccer', 'tennis', 'golf', 'yoga', 'fitness'],
            ['beauty', 'makeup'], ['business', 'industry'], ['lifestyle', 'life'],
            ['nature'], ['tutorial', 'tut', 'diy', 'do-it-yourself', 'selfmade', 'craft', 'build-it', 'diyhub'],
            ['photography', 'photo', 'photos'], ['story'], ['news', 'announcement', 'announcements'],
            ['covid-19', 'coronavirus', 'corona', 'quarantine'], ['health', 'mentalhealth', 'health-care'], 
            ['development', 'dev', 'coding', 'code'],
            ['computer', 'pc'], ['education', 'school', 'knowledge' , 'learning'],
            ['introduceyourself', 'first'], ['science', 'sci', 'biology', 'math', 'bio', 'mechanic', 'mechanics', 'physics', 'physics'],
            ['film', 'movie'], ['challenge', 'contest'],
            ['gardening', 'garden'], ['history', 'hist', 'past', 'ancient'], ['society'], ['media'],
            ['economy', 'economic', 'economics', 'market', 'marketplace'], ['future', 'thoughts'],
            ['psychology', 'psycho', 'psych'], ['family', 'fam'], ['finance', 'money', 'investing', 'investement'], 
            ['work', 'working', 'job'],
            ['philosophy'], ['culture'], ['trading', 'stock', 'stocks', 'stockmarket'],
            ['motivation', 'motivate'], ['statistics', 'stats', 'stat', 'charts']] 


BANNED_WORDS = [
    "nsfw", "cross-post", "stop_discover", "sex", "porn", "xxxwoman"
]