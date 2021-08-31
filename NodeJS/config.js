// redis Connection
const redis = require("redis");
const redisClient = redis.createClient(process.env.Redis_Port, process.env.Redis_Host);

//  - Auth
redisClient.auth(process.env.Redis_Password, (error) => {
    if(error)
        console.error(error); 
});
//  - Error Handling
redisClient.on("error", (error) => {
    if(error)
        console.error(error);
});
//  - Connection Established (Debug Infos)
redisClient.on("connect", () => {
    console.log("Connected to RedisDB");
});
//  - Has to Reconnect (Debug Infos)
redisClient.on("reconnecting", (delay) => {
    console.log("Reconnecting to RedisDB. Delay=", delay);
});


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
    "https://api.hive.blog",
    "https://api.hive.blog", // More times because it is one of the stablest one
    "https://api.hive.blog",
    "https://api.hive.blog",
    "https://api.hive.blog",
    "https://api.deathwing.me",
    "https://api.deathwing.me",
    "https://api.deathwing.me", // More times because it is one of the stablest one
    "https://api.deathwing.me",
    "https://hive-api.arcange.eu",
    "https://hived.emre.sh",
    "https://api.openhive.network",
    "https://rpc.ecency.com",
    "https://rpc.ecency.com", // More times because it is one of the stablest one
    "https://rpc.ecency.com",
    "https://rpc.ausbit.dev",
    "https://hived.privex.io",
    "https://hive.roelandp.nl",
    "https://api.pharesim.me"
]

const BANNED_WORDS = [
    "nsfw", "cross-post", "stop_discover", "sex", "porn", "xxxwoman"
]

function getRandomNode(){
    return HIVE_NODES[Math.floor(Math.random() * HIVE_NODES.length)];
}

function getTodayTimestamp(){
    const now_date = new Date(Date.now())
    const date = ("0" + now_date.getDate()).slice(-2),
        month = ("0" + (now_date.getMonth() + 1)).slice(-2),
        year = now_date.getFullYear();
    return date.toString() + "." + month.toString() + "." + year.toString();
}


function slugifyText(text) {
    text = text.toString().toLowerCase().trim();

    const sets = [
        {to: 'a', from: '[ÀÁÂÃÄÅÆĀĂĄẠẢẤẦẨẪẬẮẰẲẴẶἀ]'},
        {to: 'c', from: '[ÇĆĈČ]'},
        {to: 'd', from: '[ÐĎĐÞ]'},
        {to: 'e', from: '[ÈÉÊËĒĔĖĘĚẸẺẼẾỀỂỄỆ]'},
        {to: 'g', from: '[ĜĞĢǴ]'},
        {to: 'h', from: '[ĤḦ]'},
        {to: 'i', from: '[ÌÍÎÏĨĪĮİỈỊ]'},
        {to: 'j', from: '[Ĵ]'},
        {to: 'ij', from: '[Ĳ]'},
        {to: 'k', from: '[Ķ]'},
        {to: 'l', from: '[ĹĻĽŁ]'},
        {to: 'm', from: '[Ḿ]'},
        {to: 'n', from: '[ÑŃŅŇ]'},
        {to: 'o', from: '[ÒÓÔÕÖØŌŎŐỌỎỐỒỔỖỘỚỜỞỠỢǪǬƠ]'},
        {to: 'oe', from: '[Œ]'},
        {to: 'p', from: '[ṕ]'},
        {to: 'r', from: '[ŔŖŘ]'},
        {to: 's', from: '[ßŚŜŞŠȘ]'},
        {to: 't', from: '[ŢŤ]'},
        {to: 'u', from: '[ÙÚÛÜŨŪŬŮŰŲỤỦỨỪỬỮỰƯ]'},
        {to: 'w', from: '[ẂŴẀẄ]'},
        {to: 'x', from: '[ẍ]'},
        {to: 'y', from: '[ÝŶŸỲỴỶỸ]'},
        {to: 'z', from: '[ŹŻŽ]'},
        {to: '-', from: '[·/_,:;\']'}
    ];

    sets.forEach(set => {
        text = text.replace(new RegExp(set.from,'gi'), set.to)
    });

    return text
        .replace(/[\u0250-\ue007]/g, '') // Remove all non-latin symbols
        .replace(/--+/g, '-')    // Replace multiple - with single -
        .replace(/^-+/, '')      // Trim - from start of text
        .replace(/-+$/, '')      // Trim - from end of text       
}


module.exports = { redisClient, CATEGORIES, HIVE_NODES, BANNED_WORDS, getRandomNode, getTodayTimestamp, slugifyText };