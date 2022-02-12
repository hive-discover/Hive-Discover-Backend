const mongodb = require('../../database.js')
const hiveManager = require('./../hivemanager.js')
const stats = require('./../stats.js')
const sortings = require("../sorting.js");
const config = require("./../../config");
const amabledb = require('./../../amable-db.js')
const logging = require('./../../logging.js')

const request = require('request');
const queryParser = require('express-query-int');
const bodyParser = require('body-parser')
const express = require('express'),
router = express.Router();
router.use(bodyParser.json())
router.use(bodyParser.urlencoded({ extended: true }));
router.use(queryParser())

function parseHrtimeToSeconds(hrtime) {
    var seconds = (hrtime[0] + (hrtime[1] / 1e9)).toFixed(3);
    return seconds;
}

router.post('/posts', async (req, res) => {
    await stats.addStat(req);
    const startTime = process.hrtime();
    let countposts_text = mongodb.countDocumentsInCollection("post_text", {});

    // Get Search input
    const query_str = req.body.query, full_data = req.body.full_data, query_lang = req.body.lang;
    const amount = Math.min(parseInt(req.body.amount || 100), 1000);
    let index_name = req.body.index_name;

    if(!query_str) {
        res.send({status : "failed", err : "Query is null", code : 1}).end()
        return;
    }

    // Prepare Query and Request
    let query_obj = {query : query_str, amount : amount};
    if(query_lang)
        query_obj.lang = query_lang;
    if(index_name)
        query_obj.index_name = index_name;
    const redis_key_name = "search-post-" + query_str + "-" + query_lang + "-" + index_name + "-" + amount;
    
    const request_options = {
      'method': 'POST',
      'url': 'http://api.hive-discover.tech:' + process.env.Nsw_API_Port + '/text-searching',
      'headers': {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(query_obj)
    };
    
    new Promise((resolve, reject) => {
      // Check cached elements
      config.redisClient.get(redis_key_name, async (error, reply) => {
        // [Errors from Redis are not relevant here ==> just send the Request]
        if(reply){
          // We got a cached result
          resolve(JSON.parse(reply));
          return;
        }

        // Send query to NswAPI, retrieve response and cache it
        request(request_options, (error, response) => {
          // Response-Parsing
          if (error) reject(error);
          let body = JSON.parse(response.body);
          if(body.status === "Failed" || !body.results) reject(body.error);

          // It was scuccessful
          index_name = body.index_name
          resolve(body.results);

          // Cache posts with TTL setting (30 Minutes) [Errors are not relevant here]
          config.redisClient.set(redis_key_name, JSON.stringify(body.results), (err, reply) => {if (err) console.error(err);});
          config.redisClient.expire(redis_key_name, 60*30);
        });
      });
    }).then(async (posts) =>{
      // Check if full_data, else get only authorperm
      if(full_data){
        // Get full_data from post_raw
        const post_raw_cursor = await mongodb.findManyInCollection("post_raw", {_id : {$in : posts}})
        for await(const post of post_raw_cursor) {
          // Set on correct index
          posts.forEach((elem, index) => {
            if(elem === post._id){
              posts[index] = post.raw
            }
          });
        }   
      } else {
        // Get authorperms
        const post_info_cursor = await mongodb.findManyInCollection("post_info", {_id : {$in : posts}}, {projection : {_id : 1, author : 1, permlink : 1}})
        for await(const post of post_info_cursor){
          // Set on correct index
          posts.forEach((elem, index) => {
            if(elem === post._id){
              posts[index] = {author : post.author, permlink : post.permlink}
            }
          });           
        }
      }

      // Remove errors (when the elem is an _id (a number)) and return
      posts = posts.filter(elem => !Number.isInteger(elem));
      return posts; 
    }).then(async (posts) =>{
      // Send response
      const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
      res.send({status : "ok", posts : posts, total : await countposts_text, time : elapsedSeconds, index_name : index_name});
    }).catch(err => {
      console.error("Error in search.js/posts: " + err);
      res.send({status : "failed", err : err, code : 0}).end()
  })
});

router.post('/accounts', async (req, res) => {
    await stats.addStat(req);
    const startTime = process.hrtime();

    const query = req.body.query, raw_data = req.body.raw_data;
    const amount = Math.min(parseInt(req.body.amount), 250);

    if(query == null)
    {
        res.send({status : "failed", err : "Query is null"}).end()
        return;
    }

    // Make cursor and extract names
    cursor = await mongodb.findManyInCollection("account_info", {$text : {$search : query}})
    cursor.sort({ score: { $meta: "textScore"}}).limit(amount);
    let account_objs = [];
    for await (const account of cursor)
        account_objs.push(account.name);  

    // Get Account Jsons
    account_objs = await hiveManager.getAccounts(account_objs) 
    
    const total = await mongodb.countDocumentsInCollection("account_info", {})
    const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
    res.send({status : "ok", accounts : account_objs, total : await total, time : elapsedSeconds});
})

router.post('/similar-post', async (req, res) => {
  await stats.addStat(req);
  const startTime = process.hrtime();

  const author = req.body.author, permlink = req.body.permlink, raw_data = req.body.raw_data;
  const amount = Math.min(parseInt(req.body.amount || 7), 50);
  let index_name = req.body.index_name || "general-index";

  if(!author||!permlink)
  {
      res.send({status : "failed", err : "Query is null", code : 1}).end()
      return;
  }

  // Check if redis cached this query
  let redis_key_name = "search-similar-post-" + index_name + "-" + author + "-" + permlink + "-" + amount.toString();
  let task = new Promise((resolve, reject) => {
    config.redisClient.get(redis_key_name, async (err, reply) => {
      if(err) // We got an Error (can be ignored because it is just cache)
        console.log("Redis Client Error gets ignored: ", err);
           
      if(reply){
        // We got something cached
        resolve(JSON.parse(reply));
        return;
      } 
      
      // Get some items from CPP-NswAPI and cache it later
      // Set Options
      const options = {
        'method': 'POST',
        'url': 'http://api.hive-discover.tech:' + process.env.Nsw_API_Port + '/similar-permlink',
        'headers': {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          "amount": amount,
          "author": author,
          "permlink" : permlink,
          "index_name" : index_name
        })      
      };
    
      // Run Request to NswAPI
      request(options, (error, response) => {
        // Get body
        if (error) {
          reject(error || "An Error Occured at NswAPI!");
          return; 
        }

        const body = JSON.parse(response.body);
        if(!body.posts | body.status === "failed"){
          reject(body.error || "An Error Occured at NswAPI!");
          return;
        }

        // Resolve only posts and publish index_name
        index_name = body.index_name;
        resolve(body.posts);
        
        // Cache posts with TTL setting (30 Minutes)
        config.redisClient.set(redis_key_name, JSON.stringify(body.posts), (err, reply) => {if (err) console.error(err);});
        config.redisClient.expire(redis_key_name, 60*30);
      });          
    })
  }).then(async (similar_posts) => {
    // Get authorperms or raw post if wished
    if(raw_data){
      // Get raw posts

      for(const [lang, posts] of Object.entries(similar_posts)){
        // Set raw posts on correct indexes
        const post_raw_cursor = await mongodb.findManyInCollection("post_raw", {_id : {$in : posts}})
        for await(const post_doc of post_raw_cursor) {        
          similar_posts[lang].forEach((elem, index) => {
            if(elem === post_doc._id)
              similar_posts[lang][index] = post_doc.raw;         
          });
        }

        // Remove errors (when the elem is _id (a number))
      similar_posts[lang] = similar_posts[lang].filter(elem => !Number.isInteger(elem));
      }
    } else {
      // Get authorperms
      for(const [lang, posts] of Object.entries(similar_posts)){
        // Set authorperms on correct indexes
        const post_info_cursor = await mongodb.findManyInCollection("post_info", {_id : {$in : posts}}, {projection : {_id : 1, author : 1, permlink : 1}})
        for await(const post_doc of post_info_cursor){
          similar_posts[lang].forEach((elem, index) => {
            if(elem === post_doc._id)
              similar_posts[lang][index] = {author : post_doc.author, permlink : post_doc.permlink}           
          });           
        }

        // Remove errors (when the elem is _id (a number))
        similar_posts[lang] = similar_posts[lang].filter(elem => !Number.isInteger(elem));
      }
    }

    
    const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
    res.send({status : "ok", posts : similar_posts, time : elapsedSeconds, index_name : index_name}).end()
  })
  .catch(async (err) => {
    // Failed: check if post exists or else it is a general error
    const post_document = await mongodb.findOneInCollection("post_info", {author : author, permlink : permlink});
    if(post_document){
      // Post exists ==> general error
      console.log("Error on Handling Similar Post Search: ", err);
      res.send({status : "failed", code : 0}).end();
      return;
    }

    res.send({status : "failed", code : 2}).end();
  });;
})

router.post('/similar-account', async (req, res) => {
  await stats.addStat(req);
  const startTime = process.hrtime();

  const username = req.body.username, full_data = req.body.full_data;
  const amount = Math.min(parseInt(req.body.amount || 7), 50);

  if(!username)
  {
      res.send({status : "failed", err : "username is not available"}).end()
      return;
  }

  // Check if redis cached this query
  let redis_key_name = "search-similar-account-" + username + "-" + amount.toString();
  let task = new Promise((resolve, reject) => {
    config.redisClient.get(redis_key_name, async (err, reply) => {
      if(err) // We got an Error (can be ignored because it is just cache)
        console.log("Redis Client Error gets ignored: ", err);
           
      if(reply){
        // We got something cached
        resolve(JSON.parse(reply));
        return;
      } 
      
      // Get some items from CPP-NswAPI and cache it later
      // Set Options
      const options = {
        'method': 'POST',
        'url': 'http://api.hive-discover.tech:' + process.env.Nsw_API_Port + '/similar-accounts',
        'headers': {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          "amount": amount, 
          "account_name": username
        })      
      };
    
      // Run Request to NswAPI
      request(options, (error, response) => {
        // Get body
        if (error) {
          reject(error || "An Error Occured!");
          return; 
        }

        const body = JSON.parse(response.body);
        if(!body.accounts | body.status === "failed"){
          reject(body.error || "An Error Occured!");
          return;
        }

        // Convert to simple list and get langs              
        let accounts = [];
        Object.keys(body.accounts).forEach(key => accounts.push(body.accounts[key]));
        resolve(accounts);
        
        // Cache accounts with TTL setting (10 Minutes)
        config.redisClient.set(redis_key_name, JSON.stringify(accounts), (err, reply) => {if (err) console.error(err);});
        config.redisClient.expire(redis_key_name, 60*10);
      });          
    })
  }).then(async (accounts) => {

    // Get usernames from ids
    const account_info_cursor = await mongodb.findManyInCollection("account_info", {_id : {$in : accounts}});
    for await(const acc_doc of account_info_cursor) {
      // Set on correct index
      accounts.forEach((elem, index) => {
        if(elem === acc_doc._id)
        accounts[index] = acc_doc.name;
        
      });
    }   

    // Remove search username and then errors (when the elem is _id (a number))
    accounts = accounts.filter(elem => {return elem !== username && !Number.isInteger(elem)});

    // Get account jsons
    if(full_data)
      accounts = await hiveManager.getAccounts(accounts);  
    const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
    res.send({status : "ok", accounts : accounts, time : elapsedSeconds}).end()
  })
  .catch(err => {
    // Failed
    console.log("Error on Handling Similar Account Search: ", err);
    res.send({status : "failed"}).end();
  });;
})

router.post('/similar-by-author', async (req, res) => {
  await stats.addStat(req);
  const startTime = process.hrtime();

  const author = req.body.author, tag = req.body.tag, permlink = req.body.permlink;
  const amount = Math.min(parseInt(req.body.amount || 7), 50);

  if(!author || !permlink)
  {
      res.send({status : "failed", err : "author/permlink is not available", code : 1}).end()
      return;
  }

  // Check if redis cached this query
  let redis_key_name = "search-similar-by-author-" + author + "-" + permlink + "-" + tag + "-" + amount.toString();
  let task = new Promise((resolve, reject) => {
    config.redisClient.get(redis_key_name, async (err, reply) => {
      if(err) // We got an Error (can be ignored because it is just cache)
        console.log("Redis Client Error gets ignored: ", err);
           
      if(reply){
        // We got something cached
        resolve(JSON.parse(reply));
        return;
      } 
      
      // Get some items from CPP-NswAPI and cache it later
      // Set Options
      const options = {
        'method': 'POST',
        'url': 'http://api.hive-discover.tech:' + process.env.Nsw_API_Port + '/similar-from-author',
        'headers': {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          "amount": amount, 
          "author": author,
          "permlink": permlink,
          "tag": tag // (optional)
        })      
      };
    
      // Run Request to NswAPI
      request(options, (error, response) => {
        // Get body
        if (error) {
          reject(error || "An Error Occured!");
          return; 
        }

        const body = JSON.parse(response.body);
        if(!body.posts | body.status === "failed"){
          reject(body.error || "An Error Occured!");
          return;
        }

        resolve(body["posts"]);
        
        // Cache accounts with TTL setting (10 Minutes)
        config.redisClient.set(redis_key_name, JSON.stringify(body["posts"]), (err, reply) => {if (err) console.error(err);});
        config.redisClient.expire(redis_key_name, 60*10);
      });          
    })
  }).then(posts => {
    // Send response
    const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
    res.send({status : "ok", posts : posts, time : elapsedSeconds}).end();

    // log
    logging.writeData(logging.app_names.general_api, {"msg" : "Search - Similar By Author", "info" : {
      "author" : author,
      "permlink" : permlink,
      "amount" : amount,
      "tag" : tag,
      "success" : true
    }});
  })
  .catch(async err => {
    // Failed
    // Check if Post is in DB (exists?)
    post_info = await mongodb.findOneInCollection("post_info", {author : author, permlink : permlink}, "hive-discover");
    if(post_info === null){
      // Does not exist
      res.send({status : "failed", code : 2, msg:"Post does not exist in our DB"}).end();
      logging.writeData(logging.app_names.general_api, {"msg" : "Search - Similar By Author", "info" : {
        "author" : author,
        "permlink" : permlink,
        "amount" : amount,
        "success" : false,
        err : "Post does not exist"
      }});
      return;
    }

    // Check if post contains the tag
    post_raw = await mongodb.findOneInCollection("post_raw", {_id : post_info._id, "raw.json_metadata.tags" : tag}, "hive-discover");
    if(post_raw === null){
      // Post has not the tag
      res.send({status : "failed", code : 3, msg:"Post does not contain the tag"}).end();
      logging.writeData(logging.app_names.general_api, {"msg" : "Search - Similar By Author", "info" : {
        "author" : author,
        "permlink" : permlink,
        "amount" : amount,
        "tag" : tag,
        "success" : false,
        err : "Post does not contain the tag"
      }});
      return;
    }

    // Check if doc-vectors exist on this post
    post_data = await mongodb.findOneInCollection("post_data", {_id : post_info["_id"]}, "hive-discover");
    if(post_data === null || !post_data.doc_vectors || Object.keys(post_data.doc_vectors).length === 0){
      // No doc-vectors
      res.send({status : "failed", code : 4, msg : "No doc-vectors on this post"}).end();
      logging.writeData(logging.app_names.general_api, {"msg" : "Search - Similar By Author", "info" : {
        "author" : author,
        "permlink" : permlink,
        "amount" : amount,
        "success" : false,
        err : "Doc-Vectors not available"
      }});
      return;
    }

    // log
    logging.writeData(logging.app_names.general_api, {"msg" : "Search - Similar By Author", "info" : {
      "author" : author,
      "permlink" : permlink,
      "amount" : amount,
      "success" : false,
      err : err
    }});

    // general, unkown error
    console.log("Error on Handling Similar By Author Search: ", err);
    res.send({status : "failed", code : 0}).end();
  });;
})

router.post('/similar-in-community', async (req, res) => {
  await stats.addStat(req);
  const startTime = process.hrtime();

  const author = req.body.author, permlink = req.body.permlink;
  const amount = Math.min(parseInt(req.body.amount || 7), 50);

  if(!author || !permlink)
  {
      res.send({status : "failed", err : "author/permlink is not available", code : 1}).end()
      return;
  }

  // Check if redis cached this query
  let redis_key_name = "search-similar-in-community-" + author + "-" + permlink + "-" + amount.toString();
  let task = new Promise((resolve, reject) => {
    config.redisClient.get(redis_key_name, async (err, reply) => {
      if(err) // We got an Error (can be ignored because it is just cache)
        console.log("Redis Client Error gets ignored: ", err);
           
      if(reply){
        // We got something cached
        resolve(JSON.parse(reply));
        return;
      } 
      
      // Get some items from CPP-NswAPI and cache it later
      // Set Options
      const options = {
        'method': 'POST',
        'url': 'http://api.hive-discover.tech:' + process.env.Nsw_API_Port + '/similar-in-category',
        'headers': {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          "amount": amount, 
          "author": author,
          "permlink": permlink
        })      
      };
    
      // Run Request to NswAPI
      request(options, (error, response) => {
        // Get body
        if (error) {
          reject(error || "An Error Occured!");
          return; 
        }

        const body = JSON.parse(response.body);
        if(!body.posts | body.status === "failed"){
          reject(body.error || "An Error Occured!");
          return;
        }

        resolve(body["posts"]);
        
        // Cache accounts with TTL setting (10 Minutes)
        config.redisClient.set(redis_key_name, JSON.stringify(body["posts"]), (err, reply) => {if (err) console.error(err);});
        config.redisClient.expire(redis_key_name, 60*10);
      });          
    })
  }).then(posts => {
    // Send response
    const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
    res.send({status : "ok", posts : posts, time : elapsedSeconds}).end()

    // log
    logging.writeData(logging.app_names.general_api, {"msg" : "Search - Similar In Community", "info" : {
      "author" : author,
      "permlink" : permlink,
      "amount" : amount,
      "success" : true
    }});
  })
  .catch(async err => {
    // Failed
    // Check if Post is in DB (exists?)
    post_info = await mongodb.findOneInCollection("post_info", {author : author, permlink : permlink}, "hive-discover");
    if(post_info === null){
      // Does not exist
      res.send({status : "failed", code : 2, msg:"Post does not exist in our DB"}).end();
      logging.writeData(logging.app_names.general_api, {"msg" : "Search - Similar In Community", "info" : {
        "author" : author,
        "permlink" : permlink,
        "amount" : amount,
        "success" : false,
        err : "Post does not exist"
      }});
      return;
    }
    if(!post_info.parent_permlink || post_info.parent_permlink === ""){
      // Is no community Post
      res.send({status : "failed", code : 3, msg : "Content is no community post"}).end();
      logging.writeData(logging.app_names.general_api, {"msg" : "Search - Similar In Community", "info" : {
        "author" : author,
        "permlink" : permlink,
        "amount" : amount,
        "success" : false,
        err : "Content is no community post"
      }});
      return;
    }

    // Check if doc-vectors exist on this post
    post_data = await mongodb.findOneInCollection("post_data", {_id : post_info["_id"]}, "hive-discover");
    if(post_data === null || !post_data.doc_vectors || Object.keys(post_data.doc_vectors).length === 0){
      // No doc-vectors
      res.send({status : "failed", code : 4, msg : "No doc-vectors on this post"}).end();
      logging.writeData(logging.app_names.general_api, {"msg" : "Search - Similar In Community", "info" : {
        "author" : author,
        "permlink" : permlink,
        "amount" : amount,
        "success" : false,
        err : "Doc-Vectors not available"
      }});
      return;
    }

    // log
    logging.writeData(logging.app_names.general_api, {"msg" : "Search - Similar In Community", "info" : {
      "author" : author,
      "permlink" : permlink,
      "amount" : amount,
      "success" : false,
      err : err
    }});

    // general, unkown error
    console.log("Error on Handling Similar In Community Search: ", err);
    res.send({status : "failed", code : 0}).end();
  });;
})

router.get('/lang-overview', async (req, res) => {
  const pipeline = [ {
            '$project': {
              '_id': '$lang.lang'
            }
          }, {
            '$unwind': {
              'path': '$_id', 
              'preserveNullAndEmptyArrays': true
            }
          }, {
            '$group': {
              '_id': '$_id'
            }
    }];
  const cursor = await mongodb.aggregateInCollection("post_data", pipeline);
  let langs = await cursor.toArray();
  langs.forEach((elem, index) => langs[index] = elem._id);
  res.send({status : "ok", langs : langs})
})

module.exports = router;