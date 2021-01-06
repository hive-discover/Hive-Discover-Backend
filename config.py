
WORD2VEC_MODEL_PATH = "data/word2vec.gen"
TEXTCNN_MODEL_PATH = "data/TextCNN.pt"

MIN_KNOWN_WORDS = 10


# Database (MongoDB)
DATABASE_HOST = "192.168.178.13"
DATABASE_PORT = 27017
DATABASE_NAME = "hive-discover"

# Profiler
PROFILER_MAX_VOTES = 250
PROFILER_MAX_FEED_LEN = 5
PROFILER_MAX_FEED_POSTS_LEN = 5

# Tasks
MAX_RUNNING_TASKS = 20



class statics:
    OPEN_TASKS = []
    THREADS_RUNNING = []
    
    POST_SEARCH_AGENT = None # agents.PostSearcher
    POSTS_CATEGORY = None # agents.PostsCategory
    POSTS_MANAGER = None # hive.PostsManager
    WORD2VEC_MODEL = None
    TEXTCNN_MODEL = None




CATEGORIES = [['politic', 'politics', 'election'], ['technology', 'tech', 'technical'], ['art', 'painting', 'drawing', 'sketch'], ['animal', 'pet'], ['music'],
            ['travel'], ['fashion', 'style', 'mode', 'clothes'], ['gaming', 'game'], ['purpose'],['food', 'eat'],
            ['meat'], ['vegetarian', 'vegetable'], ['vegan'], ['recipe'], ['wisdom'], ['comedy', 'funny', 'joke'],
            ['crypto'], ['sports', 'sport'], ['training', 'train'], ['football'], ['soccer'],
            ['tennis'], ['golf'], ['yoga'], ['beauty'], ['fitness'], ['business', 'industry'], ['lifestyle', 'life'],
            ['nature'], ['tutorial', 'tut'] , ['diy', 'do-it-yourself', 'selfmade', 'craft'],
            ['photography', 'photo', 'photos'], ['story'], ['news', 'announcement', 'announcements'],
            ['covid-19', 'coronavirus', 'corona', 'quarantine'], ['health', 'mentalhealth', 'health-care'], ['coding', 'code'],
            ['computer', 'pc'], ['education', 'school', 'knowledge'], ['biology', 'bio'],
            ['introduceyourself', 'first'], ['science', 'sci'], ['film', 'movie'], ['challenge', 'contest'],
            ['gardening', 'garden'], ['hive'], ['history', 'hist', 'past', 'ancient'], ['society'], ['media'],
            ['market', 'marketplace'], ['economy', 'economic', 'economics'], ['thoughts'], ['future'], ['blockchain'],
            ['psychology', 'psycho', 'psych'], ['family', 'fam'], ['finance', 'money', 'investing', 'investement'], ['work', 'working', 'job'],
            ['philosophy'], ['culture'], ['trading', 'stock', 'stocks', 'stockmarket'],
            ['motivation', 'motivate'], ['statistics', 'stats', 'stat', 'charts'], ['development', 'dev'], 
            ['mechanic', 'mechanics'], ['physics', 'physics']] 
