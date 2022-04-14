const mongodb = require('../../database.js')
const hiveManager = require('./../hivemanager.js')
const stats = require('./../stats.js')
const sortings = require("../sorting.js");
const config = require("./../../config");
const moment = require('moment');
const logging = require('./../../logging.js')

const managed_request = require('./../../req_manager.js')
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
  
    // Required
    const query = req.body.query;

    //  * Validate Form
    if(!query) {
        res.send({status : "failed", err : "Query is null", code : 1}).end()
        return;
    }
  
    // Optional
    const amount = Math.min(Math.abs(parseInt(req.body.amount || 10)), 100);
    const page_number = Math.max(Math.abs(parseInt(req.body.page_number || 1)), 1);

    const highlight = req.body.highlight || false;
    let sort_mode = req.body.sort_mode || "relevance";

    const tags = req.body.tags || [];
    const authors = req.body.authors || [];
    const parent_permlinks = req.body.parent_permlinks || [];
    const min_votes = parseInt(req.body.min_votes || 0);
    const max_votes = parseInt(req.body.max_votes || 0);
    const wanted_langs = req.body.langs || [];
    const start_date = req.body.start_date || null;
    const end_date = req.body.end_date || null;
  
    //  * Validate Form
    if((amount * page_number) > 10000) {
        res.send({status : "failed", err : "The result length is limited to 10,000 items. So, amount * page_number has to be lower than 10,000!", code : 1}).end()
        return;
    }
    if(!Array.isArray(tags)){
      res.send({status : "failed", err : "tags is not an array", code : 1}).end()
      return;
    }
    if(!Array.isArray(authors)){
      res.send({status : "failed", err : "authors is not an array", code : 1}).end()
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
    if(start_date && !moment(start_date, "YYYY-MM-DD", true).isValid()){
      res.send({status : "failed", err : "start_date is not formatted correctly: 'YYYY-MM-DD'", code : 1}).end()
      return;
    }
    if(end_date && !moment(end_date, "YYYY-MM-DD", true).isValid()){
      res.send({status : "failed", err : "end_date is not formatted correctly: 'YYYY-MM-DD'", code : 1}).end()
      return;
    }

    // Logging
    logging.writeData(logging.app_names.general_api, {"msg" : "Post Text Search", "info" : {
      query : query,
      amount : amount,
      page_number : page_number,
      highlight : highlight,
      sort_mode : sort_mode,
      tags : tags,
      authors : authors,
      parent_permlinks : parent_permlinks,
      min_votes : min_votes,
      max_votes : max_votes,
      wanted_langs : wanted_langs,
      start_date : start_date,
      end_date : end_date
    }});

    let additional_information = []

    // Build Search Query
    const getOtherFilters = () => {
      let query = [];

      // Set tags, parent_permlink and author terms-filter
      if(parent_permlinks.length > 0)
        query.push({"terms" : {"parent_permlink" : parent_permlinks}})
      if(tags.length > 0)
        query.push({"terms" : {"tags" : tags}})
      if(authors.length > 0)
        query.push({"terms" : {"author" : authors}})

      // Set start_date and end_date range-filter
      if(start_date && !end_date)
        query.push({"range" : {"timestamp" : {"gte" : start_date}}});
      else if(!start_date && end_date)
        query.push({"range" : {"timestamp" : {"lte" : end_date}}});
      else if(start_date && end_date)
        query.push({"range" : {"timestamp" : {"lte" : end_date, "gte" : start_date}}});

      // Set wanted_langs nested-terms-filter
      if(wanted_langs.length > 0){
        query.push({
          "nested" : {
            "path" : "language",
            "query" : {
              "bool" : {
                "must" : [
                  {
                    "terms" : {
                      "language.lang" : wanted_langs
                    }
                  },
                  {
                    "range" : {
                      "language.x" : {"gte" : 0.5}
                    }
                  }
                ]
              }
            }
          }
        })
      }

      // Set min_votes and max_votes range-filter (most performance heavy)
      if(min_votes > 0 && max_votes === 0)
        query.push({ "script": { "script": {  "source":"doc['votes'].length >= " + min_votes}}});
      else if(min_votes === 0 && max_votes > 0)
        query.push({ "script": { "script": {  "source":"doc['votes'].length <= " + max_votes}}});
      else if(min_votes > 0 && max_votes > 0)
        query.push({ "script": { "script": {  "source":"doc['votes'].length >= " + min_votes + " && doc['votes'].length <= " + max_votes}}});

      return query;
    }
    const getHighlight = () => {
      if(highlight){
        return {
            pre_tags : ["<strong>"],
            post_tags : ["</strong>"],
            fields : {
              "text_body" : {},
              "text_title" : {}
            }
        }
      } else {
        return {};
      }
    
    }
    const getSortMode = () => {
      switch(sort_mode){
        case "latest":
          return {timestamp : {"order" : "desc"}};
        case "oldest":
          return {timestamp : {"order" : "asc"}};
        case "relevance":
          return { _score : { order: "desc" } };
        default:
          // Default == relevance
          additional_information.push("Unknown Sort Mode (got: '" + sort_mode + "')! Automatically changed to 'relevance'");
          sort_mode = "relevance";
          return getSortMode();
      }
    }

    const search_query = {
        "size" : amount,
        "from" : (page_number - 1) * amount,
        "query" : {
            "bool" : {
              "must" : [
                ...getOtherFilters(), 
                {
                  "multi_match" : {
                    "query" : query,
                    "fields" : ["text_title^2", "text_body"]
                  }
                }
              ]
            }
        },
        "highlight" : getHighlight(),
        "sort" : [getSortMode()],
        "_source" : {
          "includes" : ["author", "permlink"]
        }
    };

    // Make this search request
    const search_response = await new Promise(async (resolve, reject) => {
      const response = await config.osClient.search({index:"hive-post-data", body : search_query})
      if(response.statusCode === 200)
        resolve(response);

      reject(response);
    }).catch(err => {
      res.send({status : "failed", err : "Unexpected Error", code : 0}).end();

      logging.writeData(logging.app_names.general_api, {"msg" : "Error in Post Text Search", "info" : {
        error : err
      }}, 1);

      return null;
    });

    if(!search_response) return;

    // Prepare Results and send response
    let results = search_response.body.hits.hits;
    results = results.map(item => {return {author : item._source.author, permlink : item._source.permlink, score : item._score, highlight : item.highlight}});

    const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
    res.send({status : "ok", posts : results, additional_information : additional_information, time : elapsedSeconds, sort_mode : sort_mode}).end();
});

router.post('/accounts', async (req, res) => {
    await stats.addStat(req);
    const startTime = process.hrtime();

    const query = req.body.query, raw_data = req.body.raw_data;
    const amount = Math.min(parseInt(req.body.amount), 250);

    if(query == null)
    {
        res.send({status : "failed", err : "Query is null", code : 1}).end()
        return;
    }

    try{
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

      logging.writeData(logging.app_names.general_api, {"msg" : "Account Search", "info" : {
        "query" : query,
        "amount" : amount
      }});
    }catch(err){
        console.error("Error in search.js/accounts: " + err);
        res.send({status : "failed", code : 0}).end()

        // Log error
        logging.writeData(logging.app_names.general_api, {"msg" : "Account Search", "info" : {
          "query" : query,
          "amount" : amount,
          "success" : false,
          err : err
        }});
    }
})

router.post('/similar-post', async (req, res) => {
  await stats.addStat(req);
  const startTime = process.hrtime();

  // Required
  const author = req.body.author;
  const permlink = req.body.permlink;
  
  if(!author||!permlink) {
      res.send({status : "failed", err : "Query is null", code : 1}).end()
      return;
  }

  // Optional
  const amount = Math.min(parseInt(req.body.amount || 7), 50);
  const tags = req.body.tags || [];
  const parent_permlinks = req.body.parent_permlinks || [];
  const wanted_langs = req.body.langs || [];
  const minus_days = req.body.minus_days || 0;

  //  * Validate form
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
  if(!Number.isInteger(minus_days)){
    res.send({status : "failed", err : "minus_days is not a number", code : 1}).end()
    return;
  }

  // Get source post from OpenSearch
  const source_post = await new Promise(async (resolve, reject) => {
    const query = {
      "query" : {
        "bool" : {
          "must" : [
            { "term" : { "author" : author }},
            { "term" : { "permlink" : permlink }},
            { "exists" : { "field" : "doc_vector" }}
          ]
        }
      }
    };

    // Send response and resolve source / throw error when not found
    const response = await config.osClient.search({index : "hive-post-data", body : query});
    if(response.body.hits.total.value === 0) 
      reject("No post found");
    else
      resolve(response.body.hits.hits[0]._source);
  }).catch(err => {
    // Send error response
    if(err === "No post found")
      res.send({status : "failed", err : "Post not found", code : 2}).end();
    else {
      res.send({status : "failed", err : "Unknown unexpected error", code : 0}).end();
      console.error("Error in search.js/similar-post: " + err);
    }

    return null;
  });

  if(!source_post)
    return;

  logging.writeData(logging.app_names.general_api, {"msg" : "Similar Post General", "info" : {
    author : author,
    permlink : permlink,
    amount : amount,
    tags : tags,
    parent_permlinks : parent_permlinks,
    wanted_langs : wanted_langs,
    minus_days : minus_days
  }});

  // Build matching-query
  let similar_posts = await new Promise(async (resolve, reject) => {
    const get_query = (lang) => { 
      let query = {
        "size": amount,
        "query": {
            "script_score": {
                "query": {
                  "bool" : {
                    "must" : [
                      { "exists" : { "field" : "doc_vector." + lang }}
                    ]
                  }
                },
                "script": {
                    "source": "knn_score",
                    "lang": "knn",
                    "params": {
                        "field": "doc_vector." + lang,
                        "query_value": source_post.doc_vector[lang],
                        "space_type": "cosinesimil"
                    }
                }
            }
        },
        "_source": {
          "includes": [
            "author", "permlink"
          ]
        }
      }

      if(parent_permlinks.length > 0)
        query.query.script_score.query.bool.must.push({"terms" : {"parent_permlink" : parent_permlinks}})
      if(tags.length > 0)
        query.query.script_score.query.bool.must.push({"terms" : {"tags" : tags}})
      if(minus_days > 0)
        query.query.script_score.query.bool.must.push({"range" : {"timestamp" : {"gte" : "now-" + minus_days + "d"}}});

      return query;
    }

    // Start to get similar posts in each lang
    const similar_tasks = [];
    for(const lang of Object.keys(source_post.doc_vector)){
      if(wanted_langs.length > 0 && !wanted_langs.includes(lang))
        continue; // This lang is not wished

      similar_tasks.push(new Promise(async (resolve) => {
        const query = get_query(lang);
        const response = await config.osClient.search({index : "hive-post-data", body : query, timeout : "30000ms"});

        if (response.statusCode === 200)
          resolve(response.body.hits.hits);
        else
          reject(response);
      }));
    }

    // Wait for them to finish and retrieve results
    let similar_posts = await Promise.all(similar_tasks);
    similar_posts = similar_posts.flat();
    similar_posts = similar_posts.map(document => { return {score : document._score, author : document._source.author, permlink : document._source.permlink, _id : document._id};});
    similar_posts = similar_posts.filter(post => post.permlink !== permlink);
    resolve(similar_posts);
  }).catch(err => {
    res.send({status : "failed", err : "Unknown unexpected error", code : 0}).end();
    console.error("Error in search.js/similar-post: " + err);
    return null;
  })  

  if(!similar_posts)
    return;
  
  // Sort by score
  similar_posts.sort((a, b) => (a.score > b.score) ? -1 : 1);

  // Filter duplicates out and maybe slice it
  similar_post_ids = similar_posts.map(o => o._id)
  similar_posts = similar_posts.filter(({_id}, index) => !similar_post_ids.includes(_id, index + 1))
  
  if(similar_posts.length > amount)
    similar_posts = similar_posts.slice(0, amount);

  // Send response
  const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
  res.send({status : "ok", posts : similar_posts, time : elapsedSeconds}).end();
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
      const req_options = {
        'method': 'POST',
        'url': 'https://nsw-content-api.hive-discover.tech/similar-accounts',
        'headers': {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          "amount": amount, 
          "account_name": username
        })      
      };
    
      // Run Request to NswAPI
      let {error, response, body} = await managed_request(req_options, [200]);
      if(error || !body.accounts | body.status === "failed"){
        reject(error || body.error || "An Error Occured!");
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

  // Required
  const author = req.body.author;
  const permlink = req.body.permlink;
  
  if(!author||!permlink) {
      res.send({status : "failed", err : "Query is null", code : 1}).end()
      return;
  }

  // Optional
  const amount = Math.min(parseInt(req.body.amount || 7), 50);
  const tags = req.body.tags || [];
  const parent_permlinks = req.body.parent_permlinks || [];
  const wanted_langs = req.body.langs || [];
  const minus_days = req.body.minus_days || 0;

  //  * Validate form
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
  if(!Number.isInteger(minus_days)){
    res.send({status : "failed", err : "minus_days is not a number", code : 1}).end()
    return;
  }

  // Get source post from OpenSearch
  const source_post = await new Promise(async (resolve, reject) => {
    const query = {
      "query" : {
        "bool" : {
          "must" : [
            { "term" : { "author" : author }},
            { "term" : { "permlink" : permlink }},
            { "exists" : { "field" : "doc_vector" }}
          ]
        }
      }
    };

    // Send response and resolve source / throw error when not found
    const response = await config.osClient.search({index : "hive-post-data", body : query});
    if(response.body.hits.total.value === 0) 
      reject("No post found");
    else
      resolve(response.body.hits.hits[0]._source);
  }).catch(err => {
    // Send error response
    if(err === "No post found")
      res.send({status : "failed", err : "Post not found", code : 2}).end();
    else
      res.send({status : "failed", err : "Unknown unexpected error", code : 0}).end();

    console.error("Error in search.js/similar-by-author: " + err);
    return null;
  });

  if(!source_post)
    return;

  logging.writeData(logging.app_names.general_api, {"msg" : "Similar Post By Author", "info" : {
    author : author,
    permlink : permlink,
    amount : amount,
    tags : tags,
    parent_permlinks : parent_permlinks,
    wanted_langs : wanted_langs,
    minus_days : minus_days
  }});

  // Build matching-query
  let similar_posts = await new Promise(async (resolve, reject) => {
    const get_query = (lang) => { 
      let query = {
        "size": amount,
        "query": {
            "script_score": {
                "query": {
                  "bool" : {
                    "must" : [
                      { "exists" : { "field" : "doc_vector." + lang }},
                      { "term" : { "author" : { "value" : author }}},
                    ]
                  }
                },
                "script": {
                    "source": "knn_score",
                    "lang": "knn",
                    "params": {
                        "field": "doc_vector." + lang,
                        "query_value": source_post.doc_vector[lang],
                        "space_type": "cosinesimil"
                    }
                }
            }
        },
        "_source": {
          "includes": [
            "author", "permlink"
          ]
        }
      }

      if(parent_permlinks.length > 0)
        query.query.script_score.query.bool.must.push({"terms" : {"parent_permlink" : parent_permlinks}})
      if(tags.length > 0)
        query.query.script_score.query.bool.must.push({"terms" : {"tags" : tags}})
      if(minus_days > 0)
        query.query.script_score.query.bool.must.push({"range" : {"timestamp" : {"gte" : "now-" + minus_days + "d"}}});

      return query;
    }

    // Start to get similar posts in each lang
    const similar_tasks = [];
    for(const lang of Object.keys(source_post.doc_vector)){
      if(wanted_langs.length > 0 && !wanted_langs.includes(lang))
        continue; // This lang is not wished

      similar_tasks.push(new Promise(async (resolve) => {
        const query = get_query(lang);
        const response = await config.osClient.search({index : "hive-post-data", body : query, timeout : "30000ms"});

        if (response.statusCode === 200)
          resolve(response.body.hits.hits);
        else
          reject(response);
      }));
    }

    // Wait for them to finish and retrieve results
    let similar_posts = await Promise.all(similar_tasks);
    similar_posts = similar_posts.flat();
    similar_posts = similar_posts.map(document => { return {score : document._score, author : document._source.author, permlink : document._source.permlink};});
    similar_posts = similar_posts.filter(post => post.permlink !== permlink);
    resolve(similar_posts);
  }).catch(err => {
    res.send({status : "failed", err : "Unknown unexpected error", code : 0}).end();
    console.error("Error in search.js/similar-by-author: " + err);
    return null;
  })  

  if(!similar_posts)
    return;
  
  // Sort by score
  similar_posts.sort((a, b) => (a.score > b.score) ? -1 : 1);

  // Filter duplicates out
  similar_post_ids = similar_posts.map(o => o._id)
  similar_posts = similar_posts.filter(({_id}, index) => !similar_post_ids.includes(_id, index + 1))

  if(similar_posts.length > amount)
    similar_posts = similar_posts.slice(0, amount);

  // Send response
  const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
  res.send({status : "ok", posts : similar_posts, time : elapsedSeconds}).end();

  return; {
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
      const req_options = {
        'method': 'POST',
        'url': 'https://nsw-content-api.hive-discover.tech/similar-from-author',
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
      let {error, response, body} = await managed_request(req_options, [200]);
      if (error) throw error;

      // Parse response
      body = JSON.parse(body);
      if(body.status !== "ok" || !body.posts) throw body.error;

      resolve(body.posts);
        
      // Cache accounts with TTL setting (10 Minutes)
      config.redisClient.set(redis_key_name, JSON.stringify(body["posts"]), (err, reply) => {if (err) console.error(err);});
      config.redisClient.expire(redis_key_name, 60*10);         
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
  });;}
})

router.post('/category', async (req, res) => {
  await stats.addStat(req);
  const startTime = process.hrtime();

  // Required
  const categories = req.body.categories;

  //  * Validate form
  if(!categories || !Array.isArray(categories) || categories.length === 0) {
      res.send({status : "failed", err : "categories is null", code : 1}).end()
      return;
  }

  // Optional
  const amount = Math.min(parseInt(req.body.amount || 7), 50);
  const tags = req.body.tags || [];
  const parent_permlinks = req.body.parent_permlinks || [];
  const wanted_langs = req.body.langs || [];
  const minus_days = req.body.minus_days || 0;
  const min_votes = req.body.min_votes || 25;

  //  * Validate form
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
  if(!Number.isInteger(minus_days)){
    res.send({status : "failed", err : "minus_days is not a number", code : 1}).end()
    return;
  }
  if(!Number.isInteger(min_votes)){
    res.send({status : "failed", err : "min_votes is not a number", code : 1}).end()
    return;
  }

  // Build categories-list
  let categories_list = [];
  config.CATEGORIES.forEach((tags) => {
    for(let tag of tags){
      if(categories.includes(tag)){
        // This category is wished
        categories_list.push(1.01);
        return;
      }
    }

    // This category is not wished
    categories_list.push(0.01);
  })

  // Build query
  let search_query = {
    "size": amount,
    "query": {
     "script_score": {
        "query": {
          "bool" : {
            "must" : [
              // This one takes so long, it has to be the last step
              {
                "script" : {
                  "script" : "doc['votes'].length > " + min_votes
                }
              }
            ]        
          }
        },
        "script": {
          "source": "knn_score",
          "lang": "knn",
          "params": {
            "field": "categories",
            "query_value": categories_list,
            "space_type": "cosinesimil"
          }
        }
      }
    },
    "_source" : {
      "includes" : ["author", "permlink"]
    }
  }

  if(tags.length > 0)
    search_query["query"]["script_score"]["query"]["bool"]["must"].unshift({"terms" : {"tags" : tags}});  
  if(parent_permlinks.length > 0)
    search_query["query"]["script_score"]["query"]["bool"]["must"].unshift({"terms" : {"parent_permlink" : parent_permlinks}})
  if(minus_days > 0)
    search_query["query"]["script_score"]["query"]["bool"]["must"].unshift({"range" : {"timestamp" : {"gte" : "now-" + minus_days + "d"}}});

  // Search
  const response = await config.osClient.search({index : "hive-post-data", body : search_query});
  if(response.statusCode !== 200){
    res.send({status : "failed", err : "Unexpected Error occured", code : 0}).end()
    return;
  }

  // Build result and send it
  let result = response.body.hits.hits.map((post) => {return {author : post._source.author, permlink : post._source.permlink, score : post._score}});
  const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
  res.send({status : "ok", posts : result, time : elapsedSeconds}).end();

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