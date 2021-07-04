const cluster = require('cluster')
const request = require('request');
const mongodb = require('./../database.js')
const config = require('./../config')

function getVotesFromAccount(account_name, start, limit=1000){
  const dataString = JSON.stringify({
    jsonrpc : "2.0",
    method : "account_history_api.get_account_history",
    params: {"account":account_name, "start":start, "limit":limit, "operation_filter_low":1}, 
    id : 1
  });

  const options = {
    url : config.getRandomNode(),
    method : "POST",
    body: dataString
  };

  // Get data
  return new Promise((resolve, reject) => {
    request(options, (error, response, body) => {
      if(!error && response.statusCode == 200)
        resolve(body);
      else
        reject(error)
    });
  });
}

async function analyzeAccount(account_id){
  // Date from 100 days ago (limit)
  const limit_date = new Date(); 
  limit_date.setDate(limit_date.getDate() - 100);

  // Look username up
  const account_info = await mongodb.findOneInCollection("account_info", {_id : account_id});
  if(!account_info){
    // Something strange, it exists the account_data entry but no account_info document
    // --> just return
    return;
  }

  // Declare tasks-list and enter first requeest: set loading and make_feed to True
  // At the end it will be finished by await
  let tasks = [
    mongodb.updateOne("account_data", {_id : account_id}, {$set : {make_feed : true, loading : true}})
  ];

  // Process all votes (Posts are normally already in DB)
  let last_id = -1, limit = 1000;
  let running = true;
  while(running){

    await getVotesFromAccount(account_info.name, last_id, limit)
      .then(body => {
        body = JSON.parse(body);
        const history = body.result.history; 
        
        // Element 999 is the latest, so reverse iteration
        for(let i= history.length - 1; i > 0; i--){
          const id = history[i][0], transaction = history[i][1];
          const operation = transaction.op;

          // Handle vote
          if(operation.type == "vote_operation"){
            const vote = operation.value;

            // Push account_id to post_data
            tasks.push(new Promise(async (resolve) => {
              // Find post_id
              const post = await mongodb.findOneInCollection("post_info", {author : vote.author, permlink : vote.permlink});
              
              // If Post exists --> add Vote
              if(post)                
                await mongodb.updateOne("post_data", {_id : post._id}, {$addToSet : {votes : account_id}}) 

              resolve()
            }));
          }

          // Manage next ieration when last_id is now id or op_time is older than limit_date
          const op_time = new Date(Date.parse(transaction.timestamp))      
          if(last_id == id || (op_time - limit_date) < 0){
            // finished, no more
            running = false;
          }
          last_id = id;     
        }       

        limit = Math.min(1000, last_id)
      })
      .catch(async (err) => {
        console.log("Failed connection to API. Retry...")
        console.log(err);
        await new Promise((resolve) => setTimeout(resolve, 1500));
      })
  }

  // Unset loading, add make request and delete old feed
  tasks.push( mongodb.updateOne("account_data", {_id : account_id}, {"$set" :  { 
              "last_analyze" : new Date(Date.now()), "loading" : false,
              "make_feed" : true, "feed" : []}
            }));

  // Finish tasks...
  if(tasks.length > 0)
    await Promise.all(tasks);

  process.send(JSON.stringify({cmd : "finished", account_id : account_id}));
}


function setUpWorker(){
  // Set pipeline
  process.on('message', (msg) => {
    msg = JSON.parse(msg);
    if(msg.cmd == "analyze")  
      analyzeAccount(msg.account_id)
  });

  // Say I am alive/ready
  process.send(JSON.stringify({cmd: 'alive', pid : process.pid}));
}

//  *** Master Things ***
let CURRENT_ANALYZED_ACCOUNTS = []; // account._id
let AVAILABLE_WORKERS = []; // process.pid

async function masterManaging(){
  // Find requests
  const cursor = await mongodb.findManyInCollection("account_data", {analyze : true});
  let tasks = [];

  for await (const account_data of cursor){
    tasks.push(new Promise(async (resolve) => {

      // Check if it is analyzed currently
      if(account_data._id in CURRENT_ANALYZED_ACCOUNTS == false){
        // Not inside --> enter into and pass job to random worker
        CURRENT_ANALYZED_ACCOUNTS.push(account_data._id);

        // Wait to have at least one worker
        while(AVAILABLE_WORKERS.length == 0)
          await new Promise(resolve => setTimeout(resolve, 150));

        // Choose and find random (available) worker
        const worker_pid = AVAILABLE_WORKERS[Math.floor(Math.random() * AVAILABLE_WORKERS.length)];
        for(let id in cluster.workers){
          if (cluster.workers[id].process.pid === worker_pid) {
            // Found right worker --> send job

            cluster.workers[id].send(JSON.stringify({
              cmd : "analyze", account_id : account_data._id
            }));
            break
          }
        }        
      }

      // Unset analyze request
      await mongodb.updateOne("account_data", {_id : account_data._id}, {$unset : {analyze : ""}}) ;
      resolve()
    }));
  }
  
  // Endless loop with delay
  setTimeout(masterManaging, 250);

  // Wait for all to finish
  if(tasks.length > 0)
    await Promise.all(tasks);
}


//  *** Start clustering ***
const os = require('os');
const workerCount = Math.min(process.env.ANALYZER_WORKERS, os.cpus().length);

if(cluster.isMaster) {
  mongodb.logAppStart("analyzer"); // Logging

  console.log(`Taking advantage of ${workerCount} Workers`)
  console.log(`Master (Manager) PID: ${process.pid}`)

  // Fork
  for (let i = 0; i < workerCount; i++)
    cluster.fork();
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
        AVAILABLE_WORKERS = AVAILABLE_WORKERS.filter(pid => pid !== worker.process.pid)

        const nw = cluster.fork();
        console.log(`\x1b[32mWorker ${nw.process.pid} will replace him \x1b[0m`);
    }
  });

  // Set alive
  cluster.on("message", (worker, msg) => {
    msg = JSON.parse(msg);

    if(msg.cmd === "alive") {
        // Register new Worker as available
        if(msg.pid in AVAILABLE_WORKERS)
          return;
        AVAILABLE_WORKERS.push(msg.pid);
    }

    if(msg.cmd === "finished"){
      // Account is finished
      CURRENT_ANALYZED_ACCOUNTS = CURRENT_ANALYZED_ACCOUNTS.filter((id) => id !== msg.account_id);
    }
  })

  // Connect to DB and start Manager
  masterManaging();
  } else {
      // Connect to DB and set messaging service
        setUpWorker()
        .catch(err => {
          console.error(err);
          exit(1)
        });
}