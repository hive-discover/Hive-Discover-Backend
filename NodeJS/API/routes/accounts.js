const mongodb = require('../../database.js')
const apiKeys = require('./../api_keys.js')
const stats = require('./../stats.js')
const hiveManager = require('./../hivemanager.js')
const config = require('./../../config.js')
const logging = require('./../../logging.js')
const managed_request = require('./../../req_manager.js')

const similarity = require( 'compute-cosine-similarity' );

const queryParser = require('express-query-int');
const bodyParser = require('body-parser')
const express = require('express'),
router = express.Router();
router.use(bodyParser.json())
router.use(queryParser())


function parseHrtimeToSeconds(hrtime) {
  var seconds = (hrtime[0] + (hrtime[1] / 1e9)).toFixed(3);
  return seconds;
}

router.get('/', async (req, res) => {
  await stats.addStat(req);
  const username = req.query.username;
  
  // Validate form
  if(!username || username.length < 2){
    res.send({status : "failed", err : {"msg" : "Please give valid username!"}, code : 1}).end()
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
    res.send({status : "failed", err : {"msg" : "Access Token is not valid!"}, code : 2}).end()
    return;
  }

  // Get account_info
  const account_info = await account_info_task;
  if(account_info == null) {
    if(await mongodb.findOneInCollection("banned", {"name" : username})){
      // Is banned
      res.send({status : "failed", banned : true, err : {"msg" : "Account is banned"}, code : 3}).end()
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
        res.send({status : "failed", msg : "The database operation returned an error", err : err, code : 0}).end()
    })
  }

  /* Omitted because it is too complicated:
  // Find account maybe in account_data
  const account_data = await mongodb.findOneInCollection("account_data", {"_id" : account_info._id})
  if(account_data == null) {
    res.send({status : "failed",  msg : "You have to accept our Policy!", code : 4}).end()
    return;
  }*/

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

const calcFeed = async (account_id,  amount, abstraction_value, index_name = "general-index") => {
  // Request feed at CPP-NswAPI
  let options = {
    'method': 'POST',
    'url': 'https://nsw-content-api.hive-discover.tech/feed',
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

  // Run request and maybe throw error
  let {error, response, body} = await managed_request(options, [200]);
  if (error) return {"status" : "failed", error};

  body = JSON.parse(body);
  body.posts = body.posts.map(item => {return parseInt(item, 10)}) 
  return body;
}

const getFeed = async (account_id, account_username, amount, abstraction_value, tags, parent_permlinks, wanted_langs, sample_batch_size=35) => {
  // 1. Find all documents where votes=account_id or author=account_username
  const account_activities = await new Promise(async (resolve, reject) => {
    // Define both tasks
    const get_vote_task = new Promise(async (resolve) => {
      const vote_query = {
        "size" : 500,
        "sort" : [{ "timestamp" : "desc" }],
        "query" : { 
            "bool" : {
                "must" : [
                    {"term": {"votes": {"value" : account_id}}}
                ]
            }    
        },
        "_source" : {
            "includes" : [
                "doc_vector"
            ]
        }
      }

      // Get only langs the user wants OR ALL
      if(wanted_langs.length > 0){
        for(let lang of wanted_langs){
          vote_query.query.bool.must.push({"exists" : {"field" : "doc_vector." + lang}})
        }
      } else // Get all langs
        vote_query.query.bool.must.push({"exists" : {"field" : "doc_vector"}})
      

      // Send response
      const response = await config.osClient.search({index:"hive-post-data", body:vote_query});
      if(response.statusCode === 200)
        resolve(response.body.hits.hits);
      else
        reject(response);
    });
      
    const get_post_task = new Promise(async (resolve) => {
      const post_query = {
        "size" : 500,
        "sort" : [{ "timestamp" : "desc" }],
        "query" : { 
            "bool" : {
                "must" : [
                    {"term": {"author": {"value" : account_username}}}
                ]
            }    
          },
          "_source" : {
              "includes" : [
                  "doc_vector"
              ]
          }
      }

      // Get only langs the user wants OR ALL
      if(wanted_langs.length > 0){
        for(let lang of wanted_langs){
          post_query.query.bool.must.push({"exists" : {"field" : "doc_vector." + lang}})
        }
      } else // Get all langs
        post_query.query.bool.must.push({"exists" : {"field" : "doc_vector"}})

      // Send response
      const response = await config.osClient.search({index:"hive-post-data", body:post_query});
      if(response.statusCode === 200)
        resolve(response.body.hits.hits);
      else
        reject(response);
    });
    
    // Retrieve both tasks
    let account_activities = await Promise.all([get_vote_task, get_post_task]).catch(err => reject(err));
    account_activities = account_activities.flat();

    // Build activity-map and resolve it
    const activity_map = {};
    account_activities.forEach(item => {
      activity_map[item._id] = item._source.doc_vector;
    });

    resolve(activity_map);
  }).catch(err => {
    console.error("Error in Step 1 of calculating a user's feed", err);
    return null;
  })

  if(!account_activities)
    return null;
  if(Object.entries(account_activities).length === 0)
    return {}; // Nothing there

  // 2. Get a sample-batch of posts
  const get_sample_batch = () => {
    const account_activity_ids = Object.keys(account_activities);

    // Get a random sample-batch of posts (duplicates are allowed and do not matter)
    let sample_batch = [];
    for(let i=0; i < sample_batch_size; i++)
      sample_batch.push(account_activity_ids[Math.floor(Math.random() * account_activity_ids.length)]);
    return sample_batch;
  }
  const sample_batch_ids = get_sample_batch();
  
  // 3. Find similar posts to all of the sample-batch
  let similar_posts = await new Promise(async (resolve, reject) => {
    // Create Bulk-Search for search all sample-batch with knn-queries for each language

    // Define bulk-query with restrictions for tags/parent_permlink
    let bulk_query = {
      "bool" : {
        "must" : [
          {
            "range": {
              "timestamp": {
                "gte": "now-7d"
                }
            }
          }
      ]}
    }

    if(parent_permlinks.length > 0)
      bulk_query.bool.must.push({"terms" : {"parent_permlink" : parent_permlinks}})
    if(tags.length > 0)
      bulk_query.bool.must.push({"terms" : {"tags" : tags}})

    // Create bulk-body
    let bulk_body = [];
    sample_batch_ids.forEach(_id => {
      for(const lang of Object.keys(account_activities[_id])){
        bulk_body.push({"index" : "hive-post-data"});
        bulk_body.push({
          "size": 3 + abstraction_value,
          "query": {
              "script_score": {
                  "query": bulk_query,
                  "script": {
                      "source": "knn_score",
                      "lang": "knn",
                      "params": {
                          "field": "doc_vector." + lang,
                          "query_value": account_activities[_id][lang],
                          "space_type": "cosinesimil"
                      }
                  }
              }
          },
          "_source" : {
            "includes" : [
              "doc_vector." + lang, "author", "permlink"
            ]
          }
        });
      }
    });  

    // Send request
    const response = await config.osClient.msearch({body:bulk_body});
    if(response.statusCode !== 200 && response.body.responses)
      reject(response);

    // Process response (remap, flat, filter)
    let results = response.body.responses;
    results = results.map(item => {if(item.status === 200) return item.hits.hits; else return []});
    results = results.flat();
    results = results.map(item => {return {_id : item._id, _score : item._score, author : item._source.author, permlink : item._source.permlink, doc_vector : item._source.doc_vector};});
    results = results.filter(item => {return !account_activities[item._id]}); // Filter his activities out
    resolve(results);
  }).catch(err => {
    console.error("Error in Step 3 of calculating a user's feed", err);
    return null;
  });

  if(!similar_posts)
    return null;
  
  // 4. Calculate cosine-similarity between similar posts and the sample of his activities
  similar_posts.forEach((similar_post, index) => {
    // There is always only one language in these similar_posts
    if(!similar_post.doc_vector || Object.keys(similar_post.doc_vector).length === 0)
      return; // Skip if no doc_vector
    const lang = Object.keys(similar_post.doc_vector)[0];

    // Calculate cosine-similarity between similar post and his activities
    let total_cosine_similarity = 0;
    let counter = 0;
    sample_batch_ids.forEach(sample_id => {
      if(!account_activities[sample_id][lang])
        return; // Lang is not available

      const cosine_similarity = similarity(similar_post.doc_vector[lang], account_activities[sample_id][lang]);
      total_cosine_similarity += cosine_similarity + 1; // Add 1 to avoid negative numbers (OpenSearch does it automatically)
      counter += 1;
    });

    // Calc avg and add it to the normal score
    if(counter > 0)
      similar_posts[index]._score += total_cosine_similarity / counter;
  });

  // 5. Randomly sort similar posts weight by their score
  // StackOverflow Answer to a question: https://stackoverflow.com/a/65207342/7586306
  //  * Perform Exponential Distribution
  similar_posts.forEach((item, index) => {
    similar_posts[index]._score = Math.log10(1- Math.random()) / item._score;
  });
  //  * Sort by lowest score (lowest score is the best)
  similar_posts.sort((a, b) => (a._score < b._score) ? -1 : 1);
  //  * Remove duplicates
  similar_post_ids = similar_posts.map(o => o._id)
  similar_posts = similar_posts.filter(({_id}, index) => !similar_post_ids.includes(_id, index + 1))

  // 6. Reduce similar posts to the desired amount
  if(similar_posts.length > amount)
    similar_posts = similar_posts.slice(0, amount);

  // 7. Return similar posts with only author and permlink field
  return similar_posts.map(item => {return {author : item.author, permlink : item.permlink}});
}

router.get('/feed', async (req, res) => {
  await stats.addStat(req);
  const startTime = process.hrtime();

  // Required
  const username = req.query.username;
  const access_token = req.query.access_token || "unknown";
  const req_api_key = req.query.api_key || "unknown";

  // Validate required fields
  if(!username || username.length < 2){
    res.send({status : "failed", err : {"msg" : "Please give valid username/access_token!"}, code : 1}).end()
    return;
  }

  // Optional
  const amount = req.query.amount || 10;
  const abstraction_value = req.query.abstraction_value || 1;
  const tags = req.body.tags || [];
  const parent_permlinks = req.body.parent_permlinks || [];
  const wanted_langs = req.body.langs || [];
  const full_data = (req.query.full_data === 'true' || req.query.full_data === '0');

  // * Validate optional fields
  if(!amount || amount < 1 || amount > 100){
    res.send({status : "failed", err : {"msg" : "Please give valid amount: Number between 1 and 100"}, code : 1}).end();
    return;
  }
  if(!abstraction_value || abstraction_value < 1 || abstraction_value > 20){
    res.send({status : "failed", err : {"msg" : "Please give valid abstraction_value: Number between 1 and 20"}, code : 1}).end();
    return;
  }
  if(!Array.isArray(tags)){
    res.send({status : "failed", err : "tags is not an array", code : 1}).end()
    return;
  }
  if(!Array.isArray(parent_permlinks)){
    res.send({status : "failed", err : "parent_permlinks is not an array", code : 1}).end()
    return;
  }
  if(!Array.isArray(wanted_langs)){
    res.send({status : "failed", err : "langs is not an array", code : 1}).end()
    return;
  }

  // Check if user exists, that the api_key OR access_token is valid and if the user is banned
  const [account_info, api_key_check, access_token_check, ban_check] = await Promise.all([
    mongodb.findOneInCollection("account_info", {"name" : username}),
    apiKeys.checkApiKey(req_api_key),
    hiveManager.checkAccessToken(username, access_token),
    mongodb.findOneInCollection("banned", {"name" : username})
  ]);

  if(!account_info || ban_check) // User does not exist in our DB
    return res.send({status : "failed", msg : "This Account does not exist", code : 2, banned : ban_check ? true : false}).end();
  if(!api_key_check && !access_token_check) // User exists but the api_key OR access_token is invalid
    return res.send({status : "failed", err : {"msg" : "Access Token / API Key is not valid!"}, code : 5}).end()

  // Log request
  logging.writeData(logging.app_names.general_api, {"msg" : "Account Feed", "info" : {
    "name" : username,
    "amount" : amount,
    "tags" : tags,
    "parent_permlinks" : parent_permlinks,
    "wanted_langs" : wanted_langs
  }});


  // Let the feed calculation begin
  let feed_posts = await getFeed(account_info._id, username, amount, abstraction_value, tags, parent_permlinks, wanted_langs);
  if(!feed_posts)
    return res.send({status : "failed", msg : "Something went wrong", code : 0}).end();

  // Check if full_data is wished
  if(full_data){

  }

  // Return the feed
  const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
  res.send({status : "ok", posts : feed_posts, time : elapsedSeconds}).end();

  return; {
  await stats.addStat(req);
  const username = req.query.username;
  const index_name = req.query.index_name || "";
  let amount = Math.min(parseInt(req.query.amount) || 20, 250);
  const full_data = (req.query.full_data === 'true' || req.query.full_data === '0');
  const abstraction_value = parseInt(req.query.abstraction_value || 1);

  // Validate form
  if(!username || username.length < 2){
    res.send({status : "failed", err : {"msg" : "Please give valid username/access_token!"}, code : 1}).end()
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
    res.send({status : "failed", err : {"msg" : "Access Token / API Key is not valid!"}, code : 5}).end()
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
      res.send({status : "failed", banned : true, msg : "You are banned!", code : 3}).end()
      
    } else {
      res.send({status : "failed", banned : true, msg : "This Account does not exist", code : 2}).end()
    }
  }

  // Get account_data
  let account_data = await mongodb.findOneInCollection("account_data", {"_id" : account_info._id});
  if(account_data == null){
    // If not inside --> not accepted policy
    res.send({status : "failed", msg : "You have to accept our Privacy Policy!", code : 4}).end()
    return;
  }

  // account_info, account_data exists and he accepted the privacy policy
  // Get Feed
  let feed_response = await calcFeedNew(account_info._id, username, amount, abstraction_value)
    .catch(err =>{
      return {status : "failed", msg : "Something went wrong", code : 0, err : err};
    });
     
  
  if(feed_response.status !== "ok"){
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
}
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