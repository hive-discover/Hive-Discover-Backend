const CATEGORIES = [
    ['politic', 'politics', 'election'], ['technology', 'tech', 'technical', 'blockchain'], ['art', 'painting', 'drawing', 'sketch'], ['animal', 'pet'], ['music'],
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
            ['motivation', 'motivate'], ['statistics', 'stats', 'stat', 'charts']
]

const HIVE_NODES = [
    "https://api.hive.blog"
]
function getRandomNode(){
    return "https://api.hive.blog"//HIVE_NODES[Math.floor(Math.random * HIVE_NODES.length)];
}

function getTodayTimestamp(){
    const now_date = new Date(Date.now())
    const date = ("0" + now_date.getDate()).slice(-2),
        month = ("0" + (now_date.getMonth() + 1)).slice(-2),
        year = now_date.getFullYear();
    return date.toString() + "." + month.toString() + "." + year.toString();
}

module.exports = { CATEGORIES, HIVE_NODES, getRandomNode, getTodayTimestamp };