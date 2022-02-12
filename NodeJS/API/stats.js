const mongodb = require('../database.js')
const config = require('./../config.js')
const logging = require('./../logging.js')
const crypto = require('crypto');

function addStat(request){
    const url = request.baseUrl + request.url.split("?")[0];
    if(!url)
        return;

    // Get correct ip-address and hash it (sha256)
    let ip = request.headers['X-Real-IP'] || request.connection.remoteAddress;
    ip = crypto.createHash('sha256').update(ip).digest('hex');

    logging.writeData(logging.app_names.general_api, {"msg" : "Request", "info" : {
        "url" : url,
        "method" : request.method,
        "ip" : ip,
        "user-agent" : request.get('user-agent')
    }});

    // Add report to database
    const hour = new Date(Date.now()).getHours(), minutes = new Date(Date.now()).getMinutes();
    const timestamp = config.getTodayTimestamp()
    console.log(timestamp + " - " + hour.toString() + ":" + minutes.toString() + " - " + url + ` - Worker: ${process.pid}`);

    const update = {$inc : {
            ["reports." + hour.toString() + ".requests"] : 1,
            ["reports." + hour.toString() + "." + url] : 1,
        }
    }

    return mongodb.updateOne("stats", {date : timestamp}, update, upsert=true);
}


module.exports = { addStat };