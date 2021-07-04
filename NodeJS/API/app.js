//  *** Own Modules
const hiveManager = require('./hivemanager.js')
const mongodb = require('../database.js')


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

//  Own Routes
app.get('/', async (req, res) => {
  let status_obj = {status : "ok",
                    info : "Service is running", 
                    database : {accounts : 0, posts : 0, un_categorized : 0, account_data : 0, stats : 0, banned : 0}
                   }

  // Get data from DB
  await Promise.all([
    new Promise(async (resolve) => { status_obj.database.accounts = await mongodb.countDocumentsInCollection("account_info", {}); resolve() }),
    new Promise(async (resolve) => { status_obj.database.posts = await mongodb.countDocumentsInCollection("post_info", {}); resolve() }),
    new Promise(async (resolve) => { status_obj.database.un_categorized = await mongodb.countDocumentsInCollection("post_data", {categories : null}); resolve() }),
    new Promise(async (resolve) => { status_obj.database.account_data = await mongodb.countDocumentsInCollection("account_data", {}); resolve() }),
    new Promise(async (resolve) => { status_obj.database.stats = await mongodb.countDocumentsInCollection("stats", {}); resolve() }),
    new Promise(async (resolve) => { status_obj.database.banned = await mongodb.countDocumentsInCollection("banned", {}); resolve() })
  ]);

  res.send(status_obj).end()
});

// Clustering
const cluster = require('cluster');
const os = require('os');

const worker_count = Math.min(os.cpus().length, process.env.ANALYZER_WORKERS);

if(cluster.isMaster) {
  mongodb.logAppStart("api"); // Logging
  console.log(`Taking advantage of ${worker_count} Worker`)

  // Fork
  for (let i = 0; i < worker_count; i++)
    cluster.fork()

  console.dir(cluster.workers, {depth: 0});

  // Set restart event
  cluster.on('exit', (worker, code) => {
    // Good exit code is 0 :))
    // exitedAfterDisconnect ensures that it is not killed by master cluster or manually
    // if we kill it via .kill or .disconnect it will be set to true
    // \x1b[XXm represents a color, and [0m represent the end of this 
    //color in the console ( 0m sets it to white again )
    if (code !== 0 && !worker.exitedAfterDisconnect) {
        console.log(`\x1b[34mWorker ${worker.process.pid} crashed.\nStarting a new worker...\n\x1b[0m`);
        const nw = cluster.fork();
        console.log(`\x1b[32mWorker ${nw.process.pid} will replace him \x1b[0m`);
    }
  });

  console.log(`Master PID: ${process.pid}`)
} else {
  //  Start server...
  app.listen(port, () => {
    console.log(`App listening at http://localhost:${port}`)
  });
}



