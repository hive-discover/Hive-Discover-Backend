const request = require('request');
const hivejs = require('@hivechain/hivejs')
const logging = require('./../logging.js')

const mongodb = require('./../database.js')
const config = require('./../config')
const processing = require('./processing.js');

//  *** Blockchain Operations ***
async function getBlockOperations(block_nums){
    if(block_nums.length === 0)
        return '[]';

    const dataStrings = () => {
        let list = [];
        for(let i = 0; i < block_nums.length; i++){
            // Push all block_nums
            list.push({ jsonrpc : "2.0",
                        method : "condenser_api.get_ops_in_block",
                        params: [block_nums[i], false], 
                        id : (i + 1)
                    })
            }

        return JSON.stringify(list);
    }
    
    const options = {
        url : config.getRandomNode(),
        method : "POST",
        body: dataStrings()
    };

    const body = await new Promise((resolve, reject) => {
        request(options, async (error, response, body) => {
            if(!error && response.statusCode == 200)
              resolve(body);
            else {
                console.error("Cannot get Operations: ", error, body);
                await new Promise(resolve => setTimeout(()=>{resolve();}, 1500));
                process.exit(-2);   
            }
        });
    })

    return body;
}

function getCurrentBlockHeigth(){
    // Get the current latest (irreversible) block

    const dataString = JSON.stringify({
        jsonrpc : "2.0",
        method : "condenser_api.get_dynamic_global_properties",
        params: [], 
        id : 1
      });
    
      const options = {
        url : config.getRandomNode(),
        method : "POST",
        body: dataString
      };

    return new Promise(async (resolve, reject) => {
        request(options, async (error, response, body) => {
            try{
                resolve(JSON.parse(body).result.last_irreversible_block_num)              
            }catch{
                console.error("Cannot get last_irreversible_block_num: ", error, body);
                await new Promise(resolve => setTimeout(()=>{resolve();}, 1500));
                process.exit(-3);              
            }
        });
    });
} 

async function getMutedStockImageAccounts(){
    const getSomeMutedAccounts = (last_account = "") => {
        var options = {
            url: 'https://api.hive.blog',
            method: 'POST',
            body: '{"jsonrpc":"2.0", "method":"bridge.list_community_roles", "params":{"community":"hive-118554", "last":"'+last_account+'","limit":100}, "id":1}'
        };
    
        return new Promise((resolve, reject) => {
            request(options, (error, response, body) =>{
                if (!error && response.statusCode == 200 && JSON.parse(body).result) 
                    resolve(JSON.parse(body));
                else if(error)
                    reject(error);
                else
                    reject(JSON.parse(body));
            });
        });
    }  

    let last_account = "";
    while(true){
        const muted_accs = await getSomeMutedAccounts(last_account);
        if(muted_accs.result.length === 0)
            break;

        for(let i = 0; i < muted_accs.result.length; i++){
            [last_account, role, empty] = muted_accs.result[i];

            if(role !== "muted")
                continue;

            // Check if it already exists
            const exists = await mongodb.findOneInCollection("muted", {_id : last_account}, "images");
            if(exists) // Skip because it already exists
                continue; 

            // Insert in muted_accounts
            await mongodb.insertOne("muted", {_id : last_account, type : "acc"}, "images");
        }
    }

    // Remove all muted-account's posts
    const muted_accs = await mongodb.findManyInCollection("muted", { type : "acc"}, {}, "images");
    for await(const acc of muted_accs){
        // Find author's post-ids
        let his_post_ids = [];
        let cursor = await mongodb.findManyInCollection("post_info", {author : acc._id}, {projection : {_id : 1}}, "images");
        for await(const post of cursor)
            his_post_ids.push(post._id);

        if(his_post_ids.length === 0)
            continue; // Nothing to do

        // Remove all his posts
        await mongodb.deleteMany("post_info", {_id : {$in : his_post_ids}}, "images");
        await mongodb.deleteMany("post_data", {_id : {$in : his_post_ids}}, "images");
        await mongodb.deleteMany("post_text", {_id : {$in : his_post_ids}}, "images");

        // Remove img-references to his posts
        await mongodb.updateMany("img_data", {target : {$in : his_post_ids}}, {$pull : {target : {$in : his_post_ids}}}, "images");
    }

    // Run this script every hour
    setTimeout(getMutedStockImageAccounts, 1000 * 60 * 60)
    logging.writeData(logging.app_names.chain_listener, {"msg" : "Processed muted Stock Image Community accounts"});
}

//  *** Start/Main Functions ***
let currentBlockNum;
async function getStartBlockNum(){
    const doc = await mongodb.findOneInCollection("stats", {tag : "CURRENT_BLOCK_NUM"});
    if(doc && doc.current_num){
        // last blockNum is available
        currentBlockNum = doc.current_num;
    } else{
        // Nothing is available --> get current minus some buffers
        throw Error("Cannot get CURRENT_BLOCK_NUM from MongoDB");
    }
}

async function repairDatabase(batch_size=4096){
    let total_documents = await mongodb.countDocumentsInCollection("post_info", {})
    if( (await mongodb.countDocumentsInCollection("post_text", {})) === total_documents &&
        (await mongodb.countDocumentsInCollection("post_data", {})) === total_documents &&
        (await mongodb.countDocumentsInCollection("post_raw", {})) === total_documents){
        // Everything is fine
        return;
    }

    let corrupted_ids = new Set();
    console.log("Repairing Database"); 
    logging.writeData(logging.app_names.chain_listener, {"msg" : "Start Repairing our Database"});

    const check_func = (collection, ids) => {
        return new Promise(async (resolve) => {
            const cursor = await mongodb.findManyInCollection(collection, {_id : {$in : ids}}, {projection : {_id : 1}})
            const cursor_ids = await cursor.toArray();
            cursor_ids.forEach((elem, index) => cursor_ids[index] = elem._id);

            // Filter all listed out and enter all corrupted
            ids = ids.filter(elem => !cursor_ids.includes(elem));
            ids.forEach(_id => corrupted_ids.add(_id))
            resolve();
        });
    }

    // Process all ids
    let open_post_ids = [], current_task = new Promise(resolve => resolve());
    for await(const post of (await mongodb.findManyInCollection("post_info", {}, {projection : {_id : 1}}))){
        open_post_ids.push(post._id);
        total_documents--;

        // Process if the batch is full or it is the last time
        if(open_post_ids.length >= batch_size || total_documents === 0){
            await current_task;
            current_task = Promise.all([
                check_func("post_data", [...open_post_ids]),
                check_func("post_text", [...open_post_ids]),
                check_func("post_raw",  [...open_post_ids])
            ]);

            open_post_ids = [];
        }
    }

    await current_task;


    // Get authorperms and then delete ids
    corrupted_ids = Array.from(corrupted_ids);
    let authorperms = await (await mongodb.findManyInCollection("post_info", {_id : {$in : corrupted_ids}}, {projection : {author : 1, permlink : 1}})).toArray();
    await Promise.all([
        mongodb.deleteMany("post_info", {_id : {$in : corrupted_ids}}),
        mongodb.deleteMany("post_data", {_id : {$in : corrupted_ids}}),
        mongodb.deleteMany("post_text", {_id : {$in : corrupted_ids}}),
        mongodb.deleteMany("post_raw", {_id : {$in : corrupted_ids}})
    ]) 
    corrupted_ids = [];

    // Get them and reenter them
    let open_tasks = [];
    authorperms.forEach(elem => {
        open_tasks.push(new Promise(resolve => {
            hivejs.api.setOptions({ url: config.getRandomNode() });
            hivejs.api.getContent(elem.author, elem.permlink, async (err, result) => {
                if(result){
                    const task = processing.commentOperations([result]);
                    await task;
                }
                
                resolve();
            });
        }));      
    })
    

    if(open_tasks.length > 0)
        await Promise.all(open_tasks);
    console.log("Made all");
    logging.writeData(logging.app_names.chain_listener, {"msg" : "Successfully repaired our Database!"});
}

async function main(){
    if(!currentBlockNum)
        await getStartBlockNum();

    const blockHeight = await getCurrentBlockHeigth().catch(err => {return 0;});
    if(currentBlockNum >= blockHeight){
        // No blocks available, do it later again
        setTimeout(main, 2000);
        return;
    }

    // Some blocks are available
    let amount = Math.min((blockHeight - currentBlockNum), 50) // Set amount max to 50
    let requestIds = () => {
        // Return all block Ids which should be queried
        let l = [];
        for(let i = 0; i < amount; i++)
            l.push(currentBlockNum + i)
        return l;
    };

    // Get and Process all blocks
    const apiResponse = JSON.parse(await getBlockOperations(requestIds())); 
    for(let i = 0; i < apiResponse.length; i++){
        // Iterate through all blocks (apiResponse = [block1, block2, block3 ...])
        // and process them
        await processing.onBlock(apiResponse[i]);
        currentBlockNum += 1;
    }

    // Setting new CurrentBlockNum
    console.log("Settings CURRENT_BLOCK_NUM to ", currentBlockNum);
    logging.writeData(logging.app_names.chain_listener, {"msg" : "Blocks proceed", "info" : {"current_block_num" : currentBlockNum}});
    await mongodb.updateOne("stats", {tag : "CURRENT_BLOCK_NUM"}, {$set : {current_num : currentBlockNum}}).catch(err => {
        console.error("Cannot Set CurrentBlockNum, exiting and then restart");
        logging.writeData(logging.app_names.chain_listener, {"msg" : "Cannot Set CurrentBlockNum", "info" : {"err" : err}}, 1);
        process.exit(-1);
    })
    

    // Do it again in 1 Seconds because (maybe) not all Blocks are analyzed
    setTimeout(main, 1000);
}

// Start everything
logging.writeData(logging.app_names.chain_listener, {"msg" : "Starting Chain-Listener"});
repairDatabase();
getMutedStockImageAccounts();
main();
