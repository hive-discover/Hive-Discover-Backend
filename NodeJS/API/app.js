//  *** Own Modules
const hiveManager = require('./hivemanager.js')
const mongodb = require('../database.js')
const logging = require('./../logging.js')


//  *** Express API Handling
const express = require('express')
const app = express()
const port = 3000

const cors = require('cors')
app.use(cors())

//  Other Routes
app.use('/accounts', require('./routes/accounts.js'))
app.use('/search', require('./routes/search.js'))
app.use('/proxy', require('./routes/proxy.js'))
app.use('/images', require('./routes/images.js'))

//  Own Routes
app.get('/', async (req, res) => {
  const status_obj = {
    status : "ok",
    info : "Service is running",
  };

  res.send(status_obj).end()
});

app.get('/stats', async (req, res) => {
  let status_obj = {
    status : "ok",
    database : {
      accounts : 0, 
      posts : 0, 
      current_block_num : 0,
      un_categorized : 0, 
      account_data : 0, 
      stats : 0, 
      banned : 0
    }
  };

  // Get data from DB
  await Promise.all([
    new Promise(async (resolve) => { status_obj.database.accounts = await mongodb.countDocumentsInCollection("account_info", {}); resolve() }),
    new Promise(async (resolve) => { status_obj.database.posts = await mongodb.countDocumentsInCollection("post_info", {}); resolve() }),
    new Promise(async (resolve) => { status_obj.database.current_block_num = (await mongodb.findOneInCollection("stats", {"tag" : "CURRENT_BLOCK_NUM"})).current_num || 0; resolve() }),
    new Promise(async (resolve) => { status_obj.database.un_categorized = await mongodb.countDocumentsInCollection("post_data", {categories : null}); resolve() }),
    new Promise(async (resolve) => { status_obj.database.account_data = await mongodb.countDocumentsInCollection("account_data", {}); resolve() }),
    new Promise(async (resolve) => { status_obj.database.stats = await mongodb.countDocumentsInCollection("stats", {}); resolve() }),
    new Promise(async (resolve) => { status_obj.database.banned = await mongodb.countDocumentsInCollection("banned", {}); resolve() })
  ]);

  res.send(status_obj).end()
});


//  Start server...
logging.writeData(logging.app_names.general_api, {"msg" : "Starting API Server Process", "info" : {"pid" : process.pid}});

app.listen(port, () => {
  console.log(`App listening at http://localhost:${port}`)
});