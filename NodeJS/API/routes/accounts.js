const mongodb = require('../../database.js')
const apiKeys = require('./../api_keys.js')
const stats = require('./../stats.js')
const hiveManager = require('./../hivemanager.js')
const config = require('./../../config.js')
const logging = require('./../../logging.js')

const request = require('request');
const queryParser = require('express-query-int');
const bodyParser = require('body-parser')
const express = require('express'),
router = express.Router();
router.use(bodyParser.json())
router.use(queryParser())


router.get('/', async (req, res) => {
  await stats.addStat(req);
  const username = req.query.username;
  
  // Validate form
  if(!username || username.length < 2){
    res.send({status : "failed", err : {"msg" : "Please give valid username!"}}).end()
    return;
  }
  
  // Check things in Parralel
  const access_token = req.query.access_token || "unknown";
  const req_api_key = req.query.api_key || "unknown";
  let access_token_task = hiveManager.checkAccessToken(username, access_token)
  let api_key_task = apiKeys.checkApiKey(req_api_key);
  let account_info_task = mongodb.findOneInCollection("account_info", {"name" : username});

  // Check Access Token, if Test-Account or if API Key
  if(!await access_token_task && !hiveManager.checkIfTestAccount(username, access_token) && !await api_key_task){
    // Access Token is wrong and it is not the Test-Account
    res.send({status : "failed", err : {"msg" : "Access Token is not valid!"}}).end()
    return;
  }

  // Get account_info
  const account_info = await account_info_task;
  if(account_info == null) {
    if(await mongodb.findOneInCollection("banned", {"name" : username})){
      // Is banned
      res.send({status : "failed", banned : true, err : {"msg" : "Account is banned"}}).end()
      return;
    }

    // Is not banned --> create unique ID
    let account_id = null;
    while(account_id == null || await mongodb.findOneInCollection("account_info", {"_id" : account_id}))
      account_id = Math.floor(Math.random() * Math.floor(10000000))

    // Insert in account_info
    account_info = {"_id" : account_id, "name" : username};
    await mongodb.insertOne("account_info", account_info)
      .catch(err => {
        // Something failed
        res.send({status : "failed", msg : "The database operation returned an error", err : err}).end()
    })
  }

  // Find account maybe in account_data
  const account_data = await mongodb.findOneInCollection("account_data", {"_id" : account_info._id})
  if(account_data == null) {
    res.send({status : "failed",  msg : "You have to accept our Policy!"}).end()
    return;
  }

  // Get profile ==> (categories/langs)
  const get_profile = async () => {
    let categories = [], langs = [], elements = 0;

    // 1. Find posts with author=username
    let cursor =  (await mongodb.findManyInCollection("post_info", {author : username})).project({_id : 1});
    let own_post_ids = [];
    for await (const post of cursor)
      own_post_ids.push(post._id)

    // 2. Find all posts with votes=account_info._id or_id=one of own_post_ids
    cursor =  await mongodb.findManyInCollection("post_data", {$or : [{_id : {$in : own_post_ids}}, {votes : account_info._id}]});
    for await (const post of cursor){
      if(post.categories && post.lang){
        // ==> categories & lang exist
        categories.push(post.categories);
        langs.push(post.lang);
        elements += 1;

        if(account_info._id in own_post_ids){
          // Is post --> double
          categories.push(post.categories);
          langs.push(post.lang);
        }
      }
    }

    // 3. Reshape Langs and calc percentages
    let filtered_langs = [], total = 0;
    langs.forEach(item => {
      // Iterate though every post_lang
      item.forEach(obj => {
        // Iterate through every lang in post_lang
        // Check if it is in filtered, else add it
        let inside = false;
        for(let i=0; i < filtered_langs.length; i++){
          if(filtered_langs[i].lang == obj.lang){
            // Inside ==> add
            filtered_langs[i].value += obj.x;
            inside = true;
            break;
          }
        }

        if(!inside)
          filtered_langs.push({lang : obj.lang, value : obj.x});
      })
    });
    filtered_langs.forEach(item => total += item.value); 
    langs = []
    filtered_langs.forEach(item => {
      const percentage = item.value / total;
      if(percentage > 0.15) // Adding a threshold
        langs.push(item.lang);
    });
    if(langs.length == 0) // Ensure to have atlease one lang
      langs.push("en");

    // 4. Calc percentages, label categories and sort
    let filtered_categories = [];
    categories.forEach(item => {
      if(filtered_categories.length == 0)
        filtered_categories = item;
      else{
        // Add element-wise
        for(let i=0; i < filtered_categories.length; i++)
          filtered_categories[i] += item[i] / categories.length;
      }
    })
    categories = [];
    for(let i=0; i < filtered_categories.length; i++)
      categories.push({label : config.CATEGORIES[i][0], value : (filtered_categories[i])})
    
    categories.sort((a, b) => {
      // Custom sort by value
      if ( a.value < b.value )
        return 1;
      if ( a.value > b.value )
        return -1;
      return 0;
    });

    // 5.: Return calculations
    return {languages : langs, categories : categories, elements : elements}
  }

  res.send({status : "ok", msg : "Account is available", profile : (await get_profile())}).end()
})

function calcFeed(account_id,  amount, abstraction_value, index_name = "general-index"){
  // Request feed at CPP-NswAPI
  let options = {
    'method': 'POST',
    'url': 'http://api.hive-discover.tech:' + process.env.Nsw_API_Port + '/feed',
    'headers': {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      "account_id": account_id,
      "amount": amount,
      "abstraction_value": abstraction_value,
      "index_name" : index_name
    })
  
  };

  return new Promise((resolve, reject) => {
    request(options, (error, response) => {
      if (error) throw new Error(error);
      let body = JSON.parse(response.body);
      body.posts = body.posts.map(item => {return parseInt(item, 10)})
      resolve(body);
    });
  });
}

router.get('/feed', async (req, res) => {
  await stats.addStat(req);
  const username = req.query.username;
  const index_name = req.query.index_name || "";
  let amount = Math.min(parseInt(req.query.amount) || 20, 250);
  const full_data = (req.query.full_data === 'true' || req.query.full_data === '0');
  const abstraction_value = parseInt(req.query.abstraction_value || 1);

  // Validate form
  if(!username || username.length < 2){
    res.send({status : "failed", err : {"msg" : "Please give valid username/access_token!"}}).end()
    return;
  }

  // Check things in Parralel
  const access_token = req.query.access_token || "unknown";
  const req_api_key = req.query.api_key || "unknown";
  let access_token_task = hiveManager.checkAccessToken(username, access_token)
  let api_key_task = apiKeys.checkApiKey(req_api_key);
  let account_info_task = mongodb.findOneInCollection("account_info", {"name" : username});

  // Check Access Token, if it is the Test Account or api key
  if(!await access_token_task && !hiveManager.checkIfTestAccount(username, access_token) && !await api_key_task){
    res.send({status : "failed", err : {"msg" : "Access Token / API Key is not valid!"}, code : 4}).end()
    return;
  }

  // log
  logging.writeData(logging.app_names.general_api, {"msg" : "Account Feed", "info" : {
    "name" : username,
    "amount" : amount
  }});

  // Get account_info
  let account_info = await account_info_task;
  if(account_info == null) {
    // Not inside
    // --> check if banned
    if(await mongodb.findOneInCollection("banned", {"name" : username})){
      // Is banned
      res.send({status : "failed", banned : true, msg : "You are banned!", code : 2}).end()
      
    } else {
      res.send({status : "failed", banned : true, msg : "This Account does not exist", code : 1}).end()
    }

    return;
    // Is not banned --> create unique ID
    let account_id = null;
    while(account_id == null || await mongodb.findOneInCollection("account_info", {"_id" : account_id}))
      account_id = Math.floor(Math.random() * Math.floor(10000000))

    // Insert in account_info
    account_info = {"_id" : account_id, "name" : username};
    await mongodb.insertOne("account_info", account_info)
      .catch(err => {
        // Something failed
        res.send({status : "failed", msg : "The database operation returned an error", err : err}).end()
        return;
      })
  }

  // Get account_data
  let account_data = await mongodb.findOneInCollection("account_data", {"_id" : account_info._id});
  if(account_data == null){
    // If not inside --> not accepted policy
    res.send({status : "failed", msg : "You have to accept our Privacy Policy!", code : 3}).end()
    return;
  }

  // account_info, account_data exists and he accepted the privacy policy
  // Get Feed
  let feed_response = await (calcFeed(account_info._id, amount, abstraction_value, index_name))
    .catch((err) => {
      return {status : "failed", msg : "Something went wrong", code : 0, err : err};
    });
  
  if(feed_response.status === "failed"){
    res.send(feed_response).end();
    return;
  }

  // Check if full_data, else get only authorperm (Order does not matter)
  let posts = feed_response.posts;
  if(full_data){
    // Get full_data from post_raw
    const post_raw_cursor = await mongodb.findManyInCollection("post_raw", {_id : {$in : posts}});
    posts = []

    for await(const post of post_raw_cursor) 
      posts.push(post.raw);
      
  } else {
    // Get authorperms
    const post_info_cursor = await mongodb.findManyInCollection("post_info", {_id : {$in : posts}}, {projection : {_id : 1, author : 1, permlink : 1}});
    posts = [];

    for await(const post of post_info_cursor) 
      posts.push({author : post.author, permlink : post.permlink});
  }

  // Filter failed ones out and return
  posts = posts.filter(elem => !Number.isInteger(elem));
  res.send({status : "ok", posts : posts, index_name : feed_response.index_name}).end()
})

function deleteAccount(username, access_token){
  return new Promise(async (resolve, reject) => {
    // Validate form
    if(!username || username.length < 2 || !access_token || access_token.length < 10){
      reject({status : "failed", err : {"msg" : "Please give valid username/access_token!"}})
    }
    
    // Check Access Token
    if(!await hiveManager.checkAccessToken(username, access_token)){
      reject({status : "failed", err : {"msg" : "Access Token is not valid!"}})
    }

    // Get account_info
    let account_info = await mongodb.findOneInCollection("account_info", {"name" : username});
    if(account_info != null) {
      // Account is stored --> remove everything
      await Promise.all([
        // Remove Account
        new Promise(async (resolve) => {
          await mongodb.deleteMany("account_info", {_id : account_info._id});
          await mongodb.deleteMany("account_data", {_id : account_info._id});
          resolve()
        }),
        // Remove Votes
        new Promise(async (resolve) => {
          await mongodb.updateMany("post_data", {votes : account_info._id}, {$pull : {votes : account_info._id}});
          resolve();
        }),
        // Remove Posts
        new Promise(async (resolve) => {
          // Find post_ids
          cursor = await mongodb.findManyInCollection("post_info", {author : username})
          if(cursor){
            let post_ids = [];
            for await (const post of cursor) 
              post_ids.push(post._id);  
      
            // Remove all and resolve
            await Promise.all([
              new Promise(async (resolve) => {await mongodb.deleteMany("post_info", {_id : {$in : post_ids}}); resolve()}),
              new Promise(async (resolve) => {await mongodb.deleteMany("post_data", {_id : {$in : post_ids}}); resolve()}),
              new Promise(async (resolve) => {await mongodb.deleteMany("post_text", {_id : {$in : post_ids}}); resolve()})
            ]);
          }
          resolve(); 
          })
      ]).catch(err => reject({status : "failed", err : err}))
    }

    resolve({status : "ok"});
  });
}

router.get('/delete', async (req, res) => {
  await stats.addStat(req);
  const username = req.query.username, access_token = req.query.access_token;

  deleteAccount(username, access_token)
      .then(result => res.send(result))
      .catch(err => res.send({status : "failed", err : err}));
})

router.get('/ban', async (req, res) => {
  await stats.addStat(req);
  const username = req.query.username, access_token = req.query.access_token;

  // First delete and than ban username
  deleteAccount(username, access_token)
      .then(async (result) => {
        // Ban
        const banned = await mongodb.findOneInCollection("banned", {"name" : username})
        if(banned == null)
          await mongodb.insertOne("banned", {"name" : username})
        res.send({status : "ok"})
      })
      .catch(err => res.send({status : "failed", err : err}));
})


module.exports = router;