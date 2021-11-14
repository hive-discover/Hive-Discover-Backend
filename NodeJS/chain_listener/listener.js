const request = require('request');
const hivejs = require('@hivechain/hivejs')

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
        open_tasks.push(new Promise(async resolve => {
            hivejs.api.setOptions({ url: config.getRandomNode() });
            hivejs.api.getContent(elem.author, elem.permlink, async (err, result) => {
                if(result){
                    const task = handleCommentOP({
                        body : result.body,
                        title : result.title,
                        parent_author : result.parent_author,
                        json_metadata : result.json_metadata,
                        author : result.author,
                        permlink : result.permlink,
                        timestamp : result.created
                    });
                    await task;
                }
                
                resolve();
            });
        }));      
    })
    

    if(open_tasks.length > 0)
        await Promise.all(open_tasks);
    console.log("Made all");
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
    await mongodb.updateOne("stats", {tag : "CURRENT_BLOCK_NUM"}, {$set : {current_num : currentBlockNum}}).catch(err => {
        console.error("Cannot Set CurrentBlockNum, exiting and then restart");
        process.exit(-1);
    })
    

    // Do it again in 1 Seconds because (maybe) not all Blocks are analyzed
    setTimeout(main, 1000);
}

// Start everything
mongodb.logAppStart("chain-listener");
repairDatabase()
    .then(main());
