const mongodb = require('./../database.js')
const hiveManager = require('./../hivemanager.js')
const stats = require('./../stats.js')

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
    const query = req.body.query, sort = req.body.sort, full_data = req.body.full_data;
    const amount = Math.min(parseInt(req.body.amount), 250);

    if(query == null || !query.text)
    {
        res.send({status : "failed", err : "Query is null"}).end()
        return;
    }

    // Make query pipeline
    let pipeline = [{
        '$match': {
          '$text': {
            '$search': query.text
          }
        }
    }]

    // Query - before date
    if(query.before_date){
      pipeline = pipeline.concat([
        {$match : {timestamp : {$lt : new Date(Date.parse(query.before_date))}}}
      ])
    }

    // Query - after date
    if(query.after_date){
      pipeline = pipeline.concat([
        {$match : {timestamp : {$gt : new Date(Date.parse(query.after_date))}}}
      ])
    }

    // Query - lang
    if (query.lang && Array.isArray(query.lang) && query.lang.length > 0) {
      pipeline = pipeline.concat([
        { $lookup: {
            from: "post_data",
            localField: "_id",
            foreignField: "_id",
            as: "post_data"
          }
        },
        { $unwind: "$post_data" },
        { $project: { lang: "$post_data.lang" } },
        { $match: { lang: {
              $elemMatch: {
                lang: { $in: query.lang },
              }
            }
          }
        }
      ]);
    }

    // Query - author
    if (query.author && query.author.length > 2){
      query.author = query.author.replace("@", "");

      pipeline = pipeline.concat([
        { '$lookup': {
          'from': 'post_info', 
          'localField': '_id', 
          'foreignField': '_id', 
          'as': 'post_info'
        }
        }, 
        { '$unwind': '$post_info' },
        { '$match': { 'post_info.author': query.author }
      }]);
    }

    // Sort and Limit Operations
    let posts = [], sort_order = "";
    if(sort.type === "personalized" && sort.account.name && sort.account.access_token)
    {
      // Sort personalized 
      let access_toke_test = hiveManager.checkAccessToken(sort.account.name, sort.account.access_token)

      // Steps: sort by score, then limit to amount * 10 and then get only _id
      pipeline = pipeline.concat([
        { '$sort': { 
            'score': { '$meta': 'textScore' }
          }
        },
        { '$limit' : amount * 10},
        { "$project" : {_id : 1}}
      ]);

      // Start to get the AcountId
      let accountIdTask = async () => {
        let doc = await mongodb.findOneInCollection("account_info", {name : sort.account.name});
        return doc._id;
      };

      // Getting the ids
      const cursor = await mongodb.aggregateInCollection("post_text", pipeline);
      posts = await cursor.toArray();
      posts.forEach((elem, index) => {posts[index] = elem._id});

      // Send ids and account_name to Python and retrieve sorted ids
      const dataString = JSON.stringify({
        account_name : sort.account.name,
        account_id : await accountIdTask(),
        query_ids : posts
      });
    
      const options = {
        url : "http://api.hive-discover.tech:" + process.env.NMSLIB_API_Port + "/sort/personalized",
        method : "POST",
        body: dataString
      };

      // wait for result of access_token test or if it is the Test Account
      // If it fails it aborts here
      if(!(await access_toke_test) && !hiveManager.checkIfTestAccount(sort.account.name, sort.account.access_token)){
        res.send({status : "failed", err : {"msg" : "Access Token is not valid!"}}).end()
        return;
      }

      // Get sorted order from Python
      posts = await new Promise(resolve => {
        request(options, (error, response, body) => {
          try{
            body = JSON.parse(body)
            if(body.status === "ok") {
              sort_order = "personalized";
              resolve(body.result.map((item)=>{return parseInt(item);}));
              return;
            }
          }
          catch{}    

          // Fails. Return the original ids and just slice it. That is some kind of random
          sort_order = "random";
          resolve(posts);
        })
      });  
 
      // Slice array (is sorted from best to baddest)
      if(posts.length > amount)
        posts = posts.slice(0, amount);
    } else {
      if(sort === "latest"){
        // Latest
        sort_order = "latest";
        pipeline = pipeline.concat([{'$sort': {'timestamp': -1}}]);
      } else if(sort === "oldest"){
        // Oldest
        sort_order = "oldest";
        pipeline = pipeline.concat([{'$sort': {'timestamp': 1}}]);
      } else {
        // By score (default)
        sort_order = "score";
        pipeline = pipeline.concat([{
            '$sort': { 'score': { '$meta': 'textScore' } }
          }]);
      }

      // Limit, set projection and set agg to retrieve authorperm or raw_data
      pipeline = pipeline.concat([{'$limit': amount}, {"$project" : {_id : 1}}]);
      const cursor = await mongodb.aggregateInCollection("post_text", pipeline);
      posts = await cursor.toArray();
      posts.forEach((elem, index) => {posts[index] = elem._id});
    }

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

    // Remove errors (when the elem is _id (a number))
    posts = posts.filter(elem => !Number.isInteger(elem));
    const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
    res.send({status : "ok", posts : posts, total : await countposts_text, time : elapsedSeconds, sort_order : sort_order});
})

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

    if(!raw_data){
        account_objs = await hiveManager.getAccounts(account_objs)
    }
    
    const total = await mongodb.countDocumentsInCollection("account_info", {})
    const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
    res.send({status : "ok", accounts : account_objs, total : await total, time : elapsedSeconds});
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