const mongodb = require('../../database.js')
const stats = require('./../stats.js')
const config = require("./../../config");
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

router.post('/text', async (req, res) => {
  await stats.addStat(req);
  const startTime = process.hrtime();
  
  // Get Search input
  const text_query = req.body.query, full_data = req.body.full_data;
  const amount = Math.min(parseInt(req.body.amount || 100), 1000);
  let sorting = req.body.sorting || 'score';
  const redis_key_name = "search-text-image-" + text_query + "-" + amount + "-" + sorting;

  if(!text_query) {
      res.send({status : "failed", err : "Query is null", code : 1}).end()
      return;
  }

  let countposts_text = mongodb.countDocumentsInCollection("post_info", {}, "images");

  // log
  logging.writeData(logging.app_names.general_api, {"msg" : "Image - Text Search", "info" : {
    "query" : text_query,
    "amount" : amount,
    "sorting" : sorting
  }});

  // Get search results
  let nothingCached = false;
  const search_result = await new Promise((resolve, reject) => {
    config.redisClient.get(redis_key_name, (error, reply) => {
      if(error) console.log(error);
      if(!reply) 
        reject(null) // Error or nothing cached
      else
        resolve(JSON.parse(reply)); // Something cached
    });
  })
  .then(async (ids) => {
    // Something cached ==> get authorperms
    const cursor = await mongodb.findManyInCollection("post_info", {_id : {$in : ids}}, {}, "images");
    const posts = await cursor.toArray();

    // Set in order
    for(i = 0; i < posts.length; i++) {
      for(j = 0; j < ids.length; j++) {
        if(posts[i]._id != ids[j]) continue;
        // Found Spot
        ids[j] = posts[i];
        break;
      }
    }

    // Remove deleted posts (when id is just a number and not an object)
    return ids.filter(elem => !Number.isInteger(elem));
  })
  .catch(async ()=>{
    // Error or nothing cached ==> agg query
    nothingCached = true;
    let cursor;

    if(sorting === "score"){
        // Score based
        const search_pipeline = [
          {
            '$match': {
              '$text': {
                '$search': text_query
              }
            }
          }, {
            '$sort': {
              'score': {
                '$meta': 'textScore'
              }
            }
          }, {
            '$limit': amount
          }, {
            '$lookup': {
              'from': 'post_info', 
              'localField': '_id', 
              'foreignField': '_id', 
              'as': 'info'
            }
          }, {
            '$unwind': {
              'path': '$info', 
              'preserveNullAndEmptyArrays': false
            }
          }, {
            '$project': {
              'author': '$info.author', 
              'permlink': '$info.permlink', 
              'title': '$info.title', 
              'timestamp': '$info.timestamp', 
              'images': '$info.images'
            }
          }
        ]
        cursor = await mongodb.aggregateInCollection("post_text", search_pipeline, "images");
    } else {
      // Default: Comments Sentiment Based
      sorting = "smart";
      const search_pipeline = [
        {
          '$match': {
            '$text': {
              '$search': text_query
            }
          }
        }, {
          '$lookup': {
            'from': 'post_info', 
            'localField': '_id', 
            'foreignField': '_id', 
            'as': 'info'
          }
        }, {
          '$unwind': {
            'path': '$info', 
            'preserveNullAndEmptyArrays': false
          }
        }, {
          '$lookup': {
            'from': 'post_replies', 
            'localField': 'info.replies', 
            'foreignField': '_id', 
            'as': 'info.replies'
          }
        }, {
          '$project': {
            'author': '$info.author', 
            'permlink': '$info.permlink', 
            'title': '$info.title', 
            'timestamp': '$info.timestamp', 
            'images': '$info.images', 
            'score': {
              '$multiply': [
                {
                  '$meta': 'textScore'
                }, {
                  '$ifNull': [
                    {
                      '$avg': '$info.replies.sentiment'
                    }, 1
                  ]
                }
              ]
            }
          }
        }, {
          '$sort': {
            'score': -1
          }
        }
      ];
      cursor = await mongodb.aggregateInCollection("post_text", search_pipeline, "images");
    }
    return await cursor.toArray();
  });


  // Send response
  const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
  res.send({status : "ok", posts : search_result, total : await countposts_text, time : elapsedSeconds, sorting : sorting});
  
  // Cache ids in redis if not cached for 5 minutes
  if(nothingCached) {
    const ids = search_result.map(post => post._id);
    config.redisClient.set(redis_key_name, JSON.stringify(ids), 'EX', 300);
  }

  return;
  // Prepare Query and Request
  const request_options = {
    'method': 'POST',
    'url': 'http://api.hive-discover.tech:' + process.env.Image_API_Port + '/text-searching',
    'headers': {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({query : text_query, amount : amount})
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
        if(body.status !== "ok" || !body.results) reject(body.error);

        // It was scuccessful
        index_name = body.index_name
        resolve(body.results);

        // Cache posts with TTL setting (5 Minutes) [Errors are not relevant here]
        config.redisClient.set(redis_key_name, JSON.stringify(body.results), (err, reply) => {if (err) console.error(err);});
        config.redisClient.expire(redis_key_name, 60*5);
      });
    });
  }).then(async (posts) =>{
    // Check if full_data, else get only authorperm
    let cursor = null;
    if(full_data)
      cursor = await mongodb.findManyInCollection("post_info", {_id : {$in : posts}}, {}, "images")
    else
      cursor = await mongodb.findManyInCollection("post_info", {_id : {$in : posts}}, {projection : {author : 1, permlink : 1}}, "images")

    for await(const post of cursor) {
      // Set on correct index
      posts.forEach((elem, index) => {
        if(elem === post._id){
          posts[index] = post
        }
      });
    }   
    
    // Remove errors (when the elem is an _id (a number)) and return
    posts = posts.filter(elem => !Number.isInteger(elem));
    return posts; 
  }).then(async (posts) =>{
    // Send response
    const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
    res.send({status : "ok", posts : posts, total : await countposts_text, time : elapsedSeconds});
  }).catch(err => {
    console.error("Error in images.js/text: " + err);
    res.send({status : "failed", err : err, code : 0}).end()
  })
});

router.post('/similar', async (req, res) => {
    await stats.addStat(req);
    const startTime = process.hrtime();
    
    // Get Search input
    const img_desc = req.body.img_desc, full_data = req.body.full_data;
    const amount = Math.min(parseInt(req.body.amount || 100), 1000);
    const redis_key_name = "search-similar-image-" + img_desc + "-" + amount;

    if(!img_desc) {
        res.send({status : "failed", err : "Query is null", code : 1}).end()
        return;
    }

    logging.writeData(logging.app_names.general_api, {"msg" : "Image - Similar Search", "info" : {
      "img_desc" : img_desc,
      "amount" : amount
    }});
    let countposts_text = mongodb.countDocumentsInCollection("post_info", {}, "images");

    // Prepare Query and Request
    const request_options = {
      'method': 'POST',
      'url': 'http://api.hive-discover.tech:' + process.env.Image_API_Port + '/similar-searching',
      'headers': {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({query : img_desc, amount : amount})
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
          if(body.status !== "ok" || !body.results) reject(body.error);

          // It was scuccessful
          index_name = body.index_name
          resolve(body.results);

          // Cache posts with TTL setting (5 Minutes) [Errors are not relevant here]
          config.redisClient.set(redis_key_name, JSON.stringify(body.results), (err, reply) => {if (err) console.error(err);});
          config.redisClient.expire(redis_key_name, 60*5);
        });
      });
    }).then(async (posts) =>{
      // Check if full_data, else get only authorperm
      let cursor = null;
      if(full_data)
        cursor = await mongodb.findManyInCollection("post_info", {_id : {$in : posts}}, {}, "images")
      else
        cursor = await mongodb.findManyInCollection("post_info", {_id : {$in : posts}}, {projection : {author : 1, permlink : 1}}, "images")

      for await(const post of cursor) {
        // Set on correct index
        posts.forEach((elem, index) => {
          if(elem === post._id){
            posts[index] = post
          }
        });
      }   
      
      // Remove errors (when the elem is an _id (a number)) and return
      posts = posts.filter(elem => !Number.isInteger(elem));
      return posts; 
    }).then(async (posts) =>{
      // Send response
      const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
      res.send({status : "ok", posts : posts, total : await countposts_text, time : elapsedSeconds});
    }).catch(err => {
      console.error("Error in images.js/similar: " + err);
      res.send({status : "failed", err : err, code : 0}).end()
  })
});

router.get('/similar-url', async (req, res) => {
  await stats.addStat(req);
  const startTime = process.hrtime();
  
  // Get Search input
  const img_url = req.query.url;
  if(!img_url) {
      res.send({status : "failed", err : "Query is null", code : 1}).end()
      return;
  }

  logging.writeData(logging.app_names.general_api, {"msg" : "Image - Similar URL", "info" : {
    "img_url" : img_url
  }});

  // MongoDB - Aggregation to get sim_urls and then map to get only an array of just urls
  const pipeline = [
    {
      '$match': {
        'url': img_url
      }
    }, {
      '$unwind': {
        'path': '$sim', 
        'preserveNullAndEmptyArrays': false
      }
    }, {
      '$lookup': {
        'from': 'img_data', 
        'localField': 'sim', 
        'foreignField': '_id', 
        'as': 'sim'
      }
    }, {
      '$unwind': {
        'path': '$sim', 
        'preserveNullAndEmptyArrays': false
      }
    }, {
      '$project': {
        'sim_url': '$sim.url'
      }
    }, {
      '$lookup': {
        'from': 'post_info', 
        'localField': 'sim_url', 
        'foreignField': 'images', 
        'as': 'info'
      }
    }, {
      '$unwind': {
        'path': '$info', 
        'preserveNullAndEmptyArrays': false
      }
    }, {
      '$project': {
        'sim_url': 1, 
        'author': '$info.author', 
        'permlink': '$info.permlink', 
        'title': '$info.title', 
        'images': '$info.images'
      }
    }
  ]
  let sim_objs = await (await mongodb.aggregateInCollection("img_data", pipeline, "images")).toArray();

  const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
  res.send({status : "ok", sim_objs : sim_objs, time : elapsedSeconds});
  
});

router.get('/used', async (req, res) => {
  await stats.addStat(req);
  const startTime = process.hrtime();
  
  // Get Search input
  const username = req.query.username;
  const redis_key_name = "search-used-image-" + username;
  if(!username) {
      res.send({status : "failed", err : "Query is null", code : 1}).end()
      return;
  }

  logging.writeData(logging.app_names.general_api, {"msg" : "Image - Usage Data", "info" : {
    "username" : username
  }});

  // Check if it is cached
  let posts = await new Promise(resolve => {config.redisClient.get(redis_key_name, async (error, reply) => {
    if(reply) // We got a cached result
      resolve(JSON.parse(reply));
    else
      resolve([]);
    });
  });// {_id : x, img : []}

  if(posts.length === 0){
    // It is not cached, so we need to get it from the database
    // Find all images of this user
    let img_urls = new Set();
    let cursor = await mongodb.findManyInCollection("post_info", {author : username}, {}, "images");
    for await(const post of cursor)
      post.images.forEach(elem => img_urls.add(elem));

    // Remove failed images
    img_urls.delete("");
    img_urls.delete(null)
    img_urls.delete(undefined)
    img_urls.delete(" ");

    // Find all posts where at least one image from him is used
    cursor = await mongodb.findManyInCollection(
                          "post_raw", 
                          {"raw.json_metadata.image" : {"$in" : Array.from(img_urls)}, "raw.author" : {$ne : username}}, 
                          {projection : {"raw.author" : 1, "raw.permlink" : 1, "raw.title" : 1, images : "$raw.json_metadata.image", timestamp : 1}}, 
                          "hive-discover"
                        );
    for await(const post of cursor.sort({timestamp : -1})){
      let used_imgs = new Set(post.images.filter(elem => img_urls.has(elem)));
      posts.push({
        author : post.raw.author,
        permlink : post.raw.permlink,
        title : post.raw.title,
        images : Array.from(used_imgs)
      });
    }

    // Then cache for 10 min
    config.redisClient.set(redis_key_name, JSON.stringify(posts), (err, reply) => {if (err) console.error(err);});
    config.redisClient.expire(redis_key_name, 60*10);
  }
  
    
  // Send response
  const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
  res.send({status : "ok", posts : posts, time : elapsedSeconds});
  
});

router.get('/mute-post', async (req, res) => {
  await stats.addStat(req);
  
  // Get Search input
  const author = req.query.author.replace("@", "");
  const permlink = req.query.permlink.replace("/", "");
  const password = req.query.password;
  if(!author || !permlink || !password) {
      res.send({status : "failed", err : "Query is null", code : 1}).end()
      return;
  }

  // Check Password
  if(password !== process.env.IMAGE_API_MUTING_PASSWD){
    res.send({status : "failed", err : "Wrong Password", code : 2}).end()
    return;
  }

  // Check if it does exist
  const post_info = await mongodb.findOneInCollection("post_info", {author : author, permlink : permlink}, "images");
  if(!post_info) {
      res.send({status : "failed", err : "Post does not exist", code : 3}).end()
      return;
  }

  // Check if it is already muted (normally not possible)
  const muted_post = await mongodb.findOneInCollection("muted", {author : author, permlink : permlink}, "images");
  if(muted_post){
    res.send({status : "ok", msg : "Post is already muted"}).end()
    return;
  }

  // Mute and Delete the post
  await Promise.all([
    mongodb.insertOne("muted", {author : author, permlink : permlink, type : "post"}, "images"),
    mongodb.deleteMany("post_info", {_id : post_info._id}, "images"),
    mongodb.deleteMany("post_text", {_id : post_info._id}, "images"),
    mongodb.deleteMany("post_data", {_id : post_info._id}, "images")
  ]);

  // Remove dangling Images (imgs which target no post)
  const pipeline = [
    {
      '$lookup': {
        'from': 'post_info', 
        'localField': 'url', 
        'foreignField': 'images', 
        'as': 'info'
      }
    }, {
      '$match': {
        'info._id': {
          '$exists': false
        }
      }
    }, {
      '$project': {
        '_id': 1
      }
    }
  ]

  // Get Ids and Remove these dangling images
  const dangling_img_ids = await mongodb.aggregateInCollection("img_data", pipeline, "images") // Get img-ids
                                  .then(async (cursor) => {return await cursor.toArray();}) // Convert to Array
                                  .then(arr => arr.map(elem => elem._id)); // Get only the ids
  await mongodb.deleteMany("img_data", {_id : {$in : dangling_img_ids}}, "images"); 

  // Send response
  res.send({status : "ok"});
});

router.get('/mute-list', async (req, res) => {
  await stats.addStat(req);
  
  const results = await mongodb.findManyInCollection("muted", {}, {}, "images")
    .then(async (cursor) => {return await cursor.toArray();});

  // Send response
  res.send({status : "ok", result : results});
});

router.get('/post-info', async (req, res) => {
  await stats.addStat(req);
  
  // Get Search input
  const author = req.query.author.replace("@", "");
  const permlink = req.query.permlink.replace("/", "");
  if(!author || !permlink) {
      res.send({status : "failed", err : "Query is null", code : 1}).end()
      return;
  }

  const post_info = await mongodb.findOneInCollection("post_info", {author : author, permlink : permlink}, "images");
  if(!post_info) {
    res.send({status : "failed", err : "Post Not Found", code : 2}).end()
    return;
}

  const post_text = await mongodb.findOneInCollection("post_text", {_id : post_info._id}, "images");

  // Send response
  res.send({
    status : "ok", 
    result : {
      author: post_info.author,
      permlink : post_info.permlink,
      title : post_info.title,
      images : post_info.images,
      timestamp : post_info.timestamp,
      tags : post_text.text,
    }
  });
});

module.exports = router;