const mongodb = require('./../database.js')
const hiveManager = require('./../hivemanager.js')
const stats = require('./../stats.js')

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
    
    // Get Search input
    const query = req.body.query, raw_data = req.body.raw_data;
    const amount = Math.min(parseInt(req.body.amount), 50);
    let langs = req.body.lang;

    if(query == null)
    {
        res.send({status : "failed", err : "Query is null"}).end()
        return;
    }

    // Make search-pipeline
    let pipeline = [{
        '$match': {
          '$text': {
            '$search': query
          }
        }
      }, {
        '$lookup': {
          'from': 'post_data', 
          'localField': '_id', 
          'foreignField': '_id', 
          'as': 'post_data'
        }
      }, {
        '$unwind': '$post_data'
      }, {
        '$project': {
          'lang': '$post_data.lang'
    }}]

    if(langs){
        try{
            langs = JSON.parse(langs)
        } catch {}

        if(langs.length > 0){
            pipeline.push({
                '$match': {
                  'lang': {
                    '$elemMatch': {
                      'lang': {'$in' : langs}
                    }
                  }
                }
              })
            }
    }

    pipeline = pipeline.concat([
        {
            '$unset': 'lang.x'
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
              'as': 'post_info'
            }
          }, {
            '$unwind': '$post_info'
          }, {
            '$project': {
              '_id': 1, 
              'lang': 1, 
              'author': '$post_info.author', 
              'permlink': '$post_info.permlink'
            }
          }
    ]);

    // Get posts from DB
    const cursor = await mongodb.aggregateInCollection("post_text", pipeline);
    let posts = []
    await cursor.forEach(post => posts.push(post));
      
    // Check if raw_data
    if(!raw_data){
        tasks = []
        for(let i = 0; i< posts.length; i++) {
            tasks.push(hiveManager.getContent(posts[i].author, posts[i].permlink));
            await new Promise(resolve => setTimeout(() => resolve(), 50));
        }
        
        for(let i = 0; i< tasks.length; i++) {
            await tasks[i].then(result => {
                if(result && result != {}){
                    posts[i].body = result.body;
                    posts[i].title = result.title;
                    posts[i].url = result.url;
                    posts[i].created = result.created;
                    posts[i].json_metadata = result.json_metadata;
                }
            })
        }
    }

    const total = await mongodb.countDocumentsInCollection("post_text", {})
    const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
    res.send({status : "ok", posts : posts, total : total, time : elapsedSeconds});
    return;

    // Make cursor and extract ids
    cursor = await mongodb.findManyInCollection("post_text", {$text : {$search : query}})
    cursor.sort({ score: { $meta: "textScore"}, timestamp : -1}).limit(amount);
    let post_objs = [];
    for await (const post of cursor)
        post_objs.push(post._id);  

    // Get langs
    const get_langs_task = new Promise(async (resolve) => {
        let post_langs = [];
        await mongodb.findManyInCollection("post_data", {_id : {$in : post_objs}}).then(async (result) => {
            for await (const post of result) {
                // Reshape lang array and push (order does not matter)
                let lang = [];
                for(let i=0; i < post.lang.length; i++)
                    lang.push(post.lang[i].lang);
                    
                post_langs.push({_id : post._id, lang : lang});      
            }
        });
        resolve(post_langs);
    })

    // Get authorperms
    await mongodb.findManyInCollection("post_info", {_id : {$in : post_objs}}).then(result => {
        return new Promise(async (resolve) => {
            // Iterate through IDs
            for await (const post of result) {
                for (var i = 0; i < post_objs.length; i++){
                    // Set in right sport
                    if(post_objs[i] == post._id)
                        post_objs[i] = {author : post.author, permlink : post.permlink, _id : post._id};  
                }
            }
        
            resolve(); 
        });
    });

    // Get posts
    if(!raw_data){
        tasks = []
        for(let i = 0; i< post_objs.length; i++) {
        tasks.push(hiveManager.getContent(post_objs[i].author, post_objs[i].permlink));
            await new Promise(resolve => setTimeout(() => resolve(), 50));
        }
        
        for(let i = 0; i< tasks.length; i++) {
            let result = await tasks[i];
            result._id = post_objs[i]._id;
            post_objs[i] = result;
        }
    }

    // Combine post_objs with langs
    await get_langs_task.then(post_langs => {
        for(let i=0; i < post_langs.length; i++){
            // Find right post and set lang
            for (let j = 0; j < post_objs.length; j++){
                // Set in right sport
                if(post_langs[i]._id == post_objs[j]._id)
                    post_objs[j].lang = post_langs[i].lang;  
            }
        }
    });

    //const total = await mongodb.countDocumentsInCollection("post_text", {})
    //const elapsedSeconds = parseHrtimeToSeconds(process.hrtime(startTime));
    res.send({status : "ok", posts : post_objs, total : total, time : elapsedSeconds});
})

router.post('/accounts', async (req, res) => {
    await stats.addStat(req);
    const startTime = process.hrtime();

    const query = req.body.query, raw_data = req.body.raw_data;
    const amount = Math.min(parseInt(req.body.amount), 50);

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


module.exports = router;