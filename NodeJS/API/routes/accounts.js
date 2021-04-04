const mongodb = require('./../database.js')
const stats = require('./../stats.js')
const hiveManager = require('./../hivemanager.js')
const config = require('./../config.js')

const queryParser = require('express-query-int');
const bodyParser = require('body-parser')
const express = require('express'),
router = express.Router();
router.use(bodyParser.json())
router.use(queryParser())


router.get('/', async (req, res) => {
  await stats.addStat(req);
  const username = req.query.username, access_token = req.query.access_token;
  
  // Validate form
  if(!username || username.length < 2 || !access_token || access_token.length < 10){
    res.send({status : "failed", err : {"msg" : "Please give valid username/access_token!"}}).end()
    return;
  }
  
  // Check Access Token
  if(!await hiveManager.checkAccessToken(username, access_token)){
    res.send({status : "failed", err : {"msg" : "Access Token is not valid!"}}).end()
    return;
  }

  // Get account_info
  const account_info = await mongodb.findOneInCollection("account_info", {"name" : username});
  if(account_info == null) {
    if(await mongodb.findOneInCollection("banned", {"name" : username})){
      // Is banned
      res.send({status : "failed", banned : true, err : {"msg" : "Account is banned"}}).end()
      return;
    }

    // Not banned
    res.send({status : "failed", err : {"msg" : "Account is not listed"}}).end()
    return;
  }

  // Find account maybe in account_data
  const account_data = await mongodb.findOneInCollection("account_data", {"_id" : account_info._id})
  if(account_data == null) {
    res.send({status : "failed", msg : "Account is not analyzed"}).end()
    return;
  }
  let loading = false;
  if(account_data.loading && account_data.loading != false)
    loading = true;

  // Get profile ==> (categories/langs)
  const get_profile = async () => {
    let categories = [], langs = [];

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
          filtered_categories[i] += item[i]
      }
    })
    total = filtered_categories.reduce((pv, cv) => pv + cv, 0);
    categories = [];
    for(let i=0; i < filtered_categories.length; i++)
      categories.push({label : config.CATEGORIES[i][0], value : (filtered_categories[i] / total)})
    
    categories.sort((a, b) => {
      // Custom sort by value
      if ( a.value < b.value )
        return 1;
      if ( a.value > b.value )
        return -1;
      return 0;
    });

    // 5.: Return calculations
    return {languages : langs, categories : categories}
  }

  res.send({status : "ok", msg : "Account is available", loading : loading, profile : (await get_profile())}).end()
  })

router.get('/feed', async (req, res) => {
  await stats.addStat(req);
  const username = req.query.username, access_token = req.query.access_token;
  let amount = Math.min(parseInt(req.query.amount) || 20, 50);
  const raw_data = req.query.raw_data;

  // Validate form
  if(!username || username.length < 2 || !access_token || access_token.length < 10){
    res.send({status : "failed", err : {"msg" : "Please give valid username/access_token!"}}).end()
    return;
  }
  
  // Check Access Token
  if(!await hiveManager.checkAccessToken(username, access_token)){
    res.send({status : "failed", err : {"msg" : "Access Token is not valid!"}}).end()
    return;
  }

  // Get account_info
  let account_info = await mongodb.findOneInCollection("account_info", {"name" : username});
  if(account_info == null) {
    // Not inside --> But because the AccessToken is valid, it has to be a real account
    // --> check if banned
    if(await mongodb.findOneInCollection("banned", {"name" : username})){
      // Is banned
      res.send({status : "failed", banned : true, msg : "You are banned!"}).end()
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
        return;
      })
  }

  // Get account_data
  let account_data = await mongodb.findOneInCollection("account_data", {"_id" : account_info._id})
  if(account_data == null){
    // If not inside --> add and make analyze request
    account_data = {"_id" : account_info._id, analyze : true, make_feed : true, feed : []}
    await mongodb.insertOne("account_data", account_data)
      .catch(err => {
        // Something failed
        res.send({status : "failed", msg : "The database operation returned an error", err : err}).end()
        return;
      })
  }

  // Get Feed
  let post_objs = [], post_ids = [];
  if(account_data.feed && account_data.feed.length > 0){
    // Minimize if less posts available than requested
    amount = Math.min(amount, account_data.feed.length - 1);
    post_ids = account_data.feed.slice(0, amount);

    // Get authorperms
    await mongodb.findManyInCollection("post_info", {_id : {$in : post_ids}}).then(result => {
      return new Promise(async (resolve) => {
        for await (const post of result) 
          post_objs.push({author : post.author, permlink : post.permlink});  

        resolve(); 
      });
    })
  }

  // Maybe raw_data
  if(!raw_data && post_objs.length > 0){
    tasks = []
    for(let i = 0; i< post_objs.length; i++) {
      tasks.push(hiveManager.getContent(post_objs[i].author, post_objs[i].permlink));
      await new Promise(resolve => setTimeout(() => resolve(), 50));
    }
    
    for(let i = 0; i< tasks.length; i++)
      post_objs[i] = await tasks[i];
      
  }

  // Return and make_feed request
  res.send({status : "ok", msg : "", posts : post_objs}).end()
  await mongodb.updateOne("account_data", {_id : account_info._id}, {$set : {make_feed : true}, $pull : {feed : {$in : post_ids}}}) 
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