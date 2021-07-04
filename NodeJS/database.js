const { MongoClient } = require("mongodb");
const config = require("./config");

// Connection Settings
const User = process.env.MongoDB_User, Password = process.env.MongoDB_Password;
const Host = process.env.MongoDB_Host, DatabaseName = process.env.MongoDB_Name;
const url = "mongodb://" + User + ":" + Password + "@" + Host + ":27017/?authSource=admin&readPreference=primary&ssl=false"
const options = {    
    server: {    
      auto_reconnect: true,    
      socketOptions: {
        keepAlive: 30000,    
        connectTimeoutMS: 60000,    
        socketTimeoutMS: 60000,    
      }    
    }
}

var global_client = new MongoClient(url, options);

function connectToDB(callback){

  if(global_client.isConnected()) {
    // Is Connected
    callback(null, global_client);
  } else {
    // Try closing connection
    global_client.close().catch()

    // Make Connection
    global_client = new MongoClient(url, options);

    global_client.connect((err, client) => {
      if(err){
        // Failed, retry later
        console.log(err);
        setTimeout(()=>{connectToDB(callback)}, 25);
      } else {
        // Success
        global_client = client;
        callback(null, client);
      }
    });

  }
}

async function logAppStart(app_name){
  connectToDB(async (err, client) => {
    const col = client.db(DatabaseName).collection("stats");

    // Log it
    const hour = new Date(Date.now()).getHours();
    const timestamp = config.getTodayTimestamp()
    await col.updateOne({date : timestamp}, {$inc : {["starting." + hour.toString() + "." + app_name] : 1}}, upsert=true);

    await client.close()
  });
}

//  *** Find Operations ***
function findOneInCollection(collection_name, query){
    return new Promise(async (resolve, reject) => {
      connectToDB(async (err, client) => {
        database = client.db(DatabaseName);
        const col = database.collection(collection_name);
        const doc = await col.findOne(query)
        resolve(doc);
      });
    });
}

function findManyInCollection(collection_name, query, options = {}){
    return new Promise((resolve, reject) => {
      connectToDB(async (err, client) => {
        database = client.db(DatabaseName);
        let col = database.collection(collection_name);
        resolve(col.find(query, options));
      })     
    });
}
  
function countDocumentsInCollection(collection_name, query){
    return new Promise((resolve, reject) => {
      connectToDB(async (err, client) => {
        database = client.db(DatabaseName);
        let col = database.collection(collection_name);
        resolve(col.countDocuments(query));
    });
  });
}

function aggregateInCollection(collection_name, pipeline){
    return new Promise((resolve, reject) => {
      connectToDB(async (err, client) => {
        database = client.db(DatabaseName);
        let col = database.collection(collection_name);
        resolve(col.aggregate(pipeline));
    });
  });
}

  
//  *** Manipulate Operations ***
function insertOne(collection_name, document){
  return new Promise((resolve, reject) => {
    connectToDB(async (err, client) => {
      database = client.db(DatabaseName);
      let col = database.collection(collection_name);
      resolve(col.insertOne(document));
    });
  });
}

function updateOne(collection_name, query, update, upsert = false){
  return new Promise((resolve, reject) => {
    connectToDB(async (err, client) => {
      database = client.db(DatabaseName);
      let col = database.collection(collection_name);
      resolve(col.updateOne(query, update, {upsert : upsert}));
    });
  });
}

function updateMany(collection_name, query, update){
  return new Promise((resolve, reject) => {
    connectToDB(async (err, client) => {
      database = client.db(DatabaseName);
      let col = database.collection(collection_name);
      resolve(col.updateMany(query, update));
    });
  });
}

function deleteMany(collection_name, query){
  return new Promise((resolve, reject) => {
    connectToDB(async (err, client) => {
      database = client.db(DatabaseName);
      let col = database.collection(collection_name);
      resolve(col.deleteMany(query));
    });
  });
}
  
function performBulk(collection_name, bulk){
  return new Promise((resolve, reject) => {
    connectToDB(async (err, client) => {
      database = client.db(DatabaseName);
      let col = database.collection(collection_name);  
      resolve(col.bulkWrite(bulk));
    });
  });
}
  
function generateUnusedID(collection_name){
  return new Promise(async (resolve) => {
    connectToDB(async (err, client) => {
      database = client.db(DatabaseName);
      let col = database.collection(collection_name);

      while(true){    
        // Generate some random ids
        let ids = [
          Math.floor(Math.random() * 2000000000), Math.floor(Math.random() * 2000000000), Math.floor(Math.random() * 2000000000),
          Math.floor(Math.random() * 2000000000), Math.floor(Math.random() * 2000000000), Math.floor(Math.random() * 2000000000)
        ];

        // Remove all listed
        for await (const item of col.find({_id : {$in : ids}}, {_id : 1})) 
          ids = ids.filter(elem => elem != item._id);
        
        // Finished --> found unused ID
        if(ids.length > 0) {
          resolve(ids[0]);
          return;
        }
      }
    });
  });
}

module.exports = { 
  connectToDB, logAppStart,
  findOneInCollection, findManyInCollection, aggregateInCollection, 
  countDocumentsInCollection, 
  insertOne, deleteMany, updateOne, updateMany, performBulk,
  generateUnusedID 
};