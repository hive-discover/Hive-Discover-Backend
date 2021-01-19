
WORD2VEC_MODEL_PATH = "data/word2vec.gen"
FASTTEXT_MODEL_PATH = "data/fasttext/fasttext_gensim.model"
TEXTCNN_MODEL_PATH = "data/fasttext/TextCNN.pt"
LANG_FASTTEXT_MODEL = "data/fasttext-lang.ftz"

MIN_KNOWN_WORDS = 8

MAX_SEARCH_INDEX_DELTA = 60 * 60 # in seconds = 1 hour

# Database (MongoDB)
DATABASE_HOST = "192.168.178.13"
DATABASE_PORT = 27017
DATABASE_NAME = "hive-discover"

# Profiler
ACCOUNT_MAX_VOTES = 50
ACCOUNT_MAX_POSTS = 50
ACCOUNT_MAX_FEED_LEN = 30

# Tasks
MAX_RUNNING_TASKS = 20



class statics:
    OPEN_TASKS = []
    THREADS_RUNNING = []
    
    POST_SEARCH_AGENT = None # agents.PostSearcher
    POSTS_CATEGORY = None # agents.PostsCategory
    POSTS_MANAGER = None # hive.PostsManager
    ACCOUNTS_MANAGER = None # hive.AccountsManager
    ACCOUNTS_SEARCHER = None # agents.AccountsSearcher
    LANG_DETECTOR = None # network.LangDetector

    WORD2VEC_MODEL = None
    FASTTEXT_MODEL = None # KeyedVectors
    TEXTCNN_MODEL = None 
    LEMMATIZER = None




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