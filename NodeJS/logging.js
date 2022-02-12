const mongodb = require('./database.js')

module.exports.app_names = Object.freeze({
    // App Names : Collection Names in Logging-DB
    "general_api" : "general_api",
    "chain_listener" : "chain_listener",
})


module.exports.writeData = async (app_name, data, status_code=0) => {
    // Add Timestamp and Status-Code to Data
    data.timestamp = new Date();
    data.status_code = status_code;

    // Enter in correct collection
    await mongodb.insertOne(app_name, data, "logging");
}
