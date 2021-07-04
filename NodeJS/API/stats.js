const mongodb = require('../database.js')
const config = require('./../config.js')


function addStat(request){
    const url = request.originalUrl;
    if(!url)
        return;
    const hour = new Date(Date.now()).getHours(), minutes = new Date(Date.now()).getMinutes();
    const timestamp = config.getTodayTimestamp()
    console.log(timestamp + " - " + hour.toString() + ":" + minutes.toString() + " - " + url + ` - Worker: ${process.pid}`);

    const update = {$inc : {["reports." + hour.toString() + ".requests"] : 1}}
    // Accounts
    if(url.includes("/accounts") && url.includes("/feed") == false && url.includes("/delete") == false && url.includes("/ban") == false)
        update.$inc["reports." + hour.toString() + ".account_data_queries"] = 1;
    if(url.includes("/accounts/feed"))
        update.$inc["reports." + hour.toString() + ".feed_requests"] = 1;
    if(url.includes("/accounts/delete"))
        update.$inc["reports." + hour.toString() + ".delete_requests"] = 1;
    if(url.includes("/accounts/ban"))
        update.$inc["reports." + hour.toString() + ".ban_requests"] = 1;

    // Search
    if(url.includes("/search/accounts"))
        update.$inc["reports." + hour.toString() + ".account_queries"] = 1;
    if(url.includes("/search/posts"))
        update.$inc["reports." + hour.toString() + ".post_queries"] = 1;

    if(url.includes("/proxy"))
        update.$inc["reports." + hour.toString() + ".proxy_used"] = 1;

    return mongodb.updateOne("stats", {date : timestamp}, update, upsert=true);
}


module.exports = { addStat };