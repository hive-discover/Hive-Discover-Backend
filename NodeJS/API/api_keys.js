const config = require("../config.js")
const mongodb = require('../database.js')
const crypto = require('crypto');

module.exports.checkApiKey = (api_key) => {
    return new Promise(resolve => {
        if(api_key === "unknown"){
            resolve(false);
             return;
        }
        const hashed_api_key = crypto.createHash("sha256").update(api_key).digest("base64");
        const redis_key_name = "api_key-" + hashed_api_key;

        config.redisClient.get(redis_key_name, async (err, reply) => {
            if(reply) {
                resolve(true);
            } else {
                // Not correct or not cached ==> check in MongoDB
                let doc = await (mongodb.findOneInCollection("api_keys", {key: api_key}));
                if(doc) {
                    resolve(true);

                    // Add Entry to Redis
                    config.redisClient.set(redis_key_name, "true", (err, reply) => {
                        if(err)
                            console.error(err);
                    });
                    config.redisClient.expire(redis_key_name, 60*60*24 * 7);     // 7 days            
                } else {
                    // Wrong Token
                    resolve(false);
                }
            }
    });
});
}
