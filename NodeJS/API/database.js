const { MongoClient } = require("mongodb");

// Connection Settings
const User = process.env.MongoDB_User, Password = process.env.MongoDB_Password;
const Host = process.env.MongoDB_Host, DatabaseName = process.env.MongoDB_Name;
const url = "mongodb://" + User + ":" + Password + "@" + Host + ":27017/?authSource=admin&readPreference=primary&ssl=false"
const options = {    
    server: {    
      auto_reconnect: true,    
      socketOptions: {
        keepAlive: 1,    
        connectTimeoutMS: 60000,    
        socketTimeoutMS: 60000,    
      }    
    }
}

var client = new MongoClient(url, options);



async function connectToDB(){
    await client.connect()
    await client.db("admin").command({ ping: 1 })
    
    console.log("Connected successfully to MongoDB instance")
    return true
}

//  *** Find Operations ***
async function findOneInCollection(collection_name, query){
    database = client.db(DatabaseName);
    const col = database.collection(collection_name);
    const doc = await col.findOne(query)
    return doc;
}

function findManyInCollection(collection_name, query, options = {}){
  return new Promise((resolve, reject) => {
    database = client.db(DatabaseName);
    let col = database.collection(collection_name);
    resolve(col.find(query, options));
  });
}

function aggregateInCollection(collection_name, pipeline){
  return new Promise((resolve, reject) => {
    database = client.db(DatabaseName);
    let col = database.collection(collection_name);
    resolve(col.aggregate(pipeline));
  });
}

function countDocumentsInCollection(collection_name, query){
  return new Promise((resolve, reject) => {
    database = client.db(DatabaseName);
    let col = database.collection(collection_name);
    resolve(col.countDocuments(query));
  });
}

//  *** Manipulate Operations ***
function insertOne(collection_name, document){
  return new Promise((resolve, reject) => {
    database = client.db(DatabaseName);
    let col = database.collection(collection_name);
    resolve(col.insertOne(document));
  });
}

function updateOne(collection_name, query, update, upsert = false){
  return new Promise((resolve, reject) => {
    database = client.db(DatabaseName);
    let col = database.collection(collection_name);
    resolve(col.updateOne(query, update, {upsert : upsert}));
  });
}

function updateMany(collection_name, query, update){
  return new Promise((resolve, reject) => {
    database = client.db(DatabaseName);
    let col = database.collection(collection_name);
    resolve(col.updateMany(query, update));
  });
}

function deleteMany(collection_name, query){
  return new Promise((resolve, reject) => {
    database = client.db(DatabaseName);
    let col = database.collection(collection_name);
    resolve(col.deleteMany(query));
  });
}


module.exports = { connectToDB, findOneInCollection, findManyInCollection, aggregateInCollection, countDocumentsInCollection, insertOne, updateOne, updateMany, deleteMany };