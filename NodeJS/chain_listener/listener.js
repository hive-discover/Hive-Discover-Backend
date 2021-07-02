const request = require('request');
const HTMLParser = require('node-html-parser');
const hivejs = require('@hivechain/hivejs')
const MarkdownIt = require('markdown-it')
const md = new MarkdownIt();

const mongodb = require('./../database.js')
const config = require('./../config')

//  *** Blockchain Operations ***
function getBlockOperations(block_nums){
    if(block_nums.length === 0)
        return '[]';

    const dataStrings = function () {
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

    return new Promise((resolve, reject) => {
        request(options, (error, response, body) => {
            if(!error && response.statusCode == 200)
              resolve(body);
            else
              reject(error)
          });
    });
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

    return new Promise((resolve, reject) => {
        request(options, (error, response, body) => {
            if(!error && response.statusCode == 200) 
                resolve(JSON.parse(body).result.last_irreversible_block_num)  
            else
                resolve(0)
          });
    });
} 

// Arrays for bulk operations
let bulks_account_data = [], bulks_account_info = [];
let bulks_post_data = [], bulks_post_info = [], bulks_post_text = [];

//  *** Operation Handlers ***
function handleCommentOP(op_value){
    return new Promise(async (resolve) => {
        if(op_value.parent_author !== ""){
            // Is comment
            resolve();
            return;
        }

        // Get later unused id and check if it exists
        const getUnusedID_task = mongodb.generateUnusedID("post_info");

        // Check if banned (post or user) OR if it's exists
        if( await mongodb.findOneInCollection("banned", {author : op_value.author, permlink: op_value.permlink}) || 
            await mongodb.findOneInCollection("banned", {name : op_value.author}) ||
            await mongodb.findOneInCollection("post_info", {author : op_value.author, permlink: op_value.permlink})) {
            // Is banned / already exists
            resolve();
            return;
        }

        // Start preparing the Post
        try{
            op_value.json_metadata = JSON.parse(op_value.json_metadata)
        } catch {
            // JSON Parse error --> set to {} because it is usually '' then
            op_value.json_metadata = {}
        }
        
        if(!op_value.json_metadata.tags) 
            op_value.json_metadata.tags = [];
        if(!op_value.json_metadata.image) 
            op_value.json_metadata.image = [];
        let raw_post = {...op_value}

        if(Array.isArray(op_value.json_metadata.tags))
            op_value.json_metadata.tags = op_value.json_metadata.tags.join(" ");

        // Check banned Words
        var isbanned = false;
        config.BANNED_WORDS.forEach((item)=>{
            if(
                op_value.body.indexOf(item) >= 0 || 
                op_value.json_metadata.tags.indexOf(item) >= 0 ||
                op_value.title.indexOf(item) >= 0
            ){
                // Not enter
                isbanned = true;
                resolve();
            }
        });
        if(isbanned)
            return;

        // Parse body and extract images
        let html_body = md.render(op_value.body);
        let root = HTMLParser.parse(html_body);  
        const imgs = root.querySelectorAll('img')
        for(let i = 0; i < imgs.length; i ++)
        {    
            let src = imgs[i].attrs.src
            if(!src in op_value.json_metadata.image)
                op_value.json_metadata.image.push(src)
        }

        // Reparse to only get text
        root = HTMLParser.parse(root.text);
        op_value.body = root.text;   
        const plain_body = op_value.body;
        op_value.body = config.slugifyText(op_value.body); // replaceAll non-latin
        op_value.title = config.slugifyText(op_value.title); // replaceAll non-latin
        op_value.json_metadata.tags = config.slugifyText(op_value.json_metadata.tags); // replaceAll non-latin

        if(op_value.body.split(' ').length < 10) {
            // Too low words
            resolve();
            return;
        }

        if(op_value.timestamp)
            op_value.timestamp = new Date(Date.parse(op_value.timestamp));
        else 
            op_value.timestamp = new Date(Date.now());

        // Prepare documents. Timestamp just now becuase op_value does not have it but because it is the latest block it matches it (nearly)
        const post_id = await getUnusedID_task;
        const post_info_doc = {_id : post_id, author : op_value.author, permlink : op_value.permlink, timestamp : op_value.timestamp};
        const post_text_doc = {_id : post_id, title : op_value.title, body : op_value.body, tag_str : op_value.json_metadata.tags, timestamp : op_value.timestamp}
        const post_data_doc = {_id : post_id, categories : null, lang : null, timestamp : op_value.timestamp}
        raw_post.json_metadata = op_value.json_metadata;
        const post_raw_doc = {_id : post_id, timestamp : op_value.timestamp, raw : raw_post, plain : {body : plain_body}}

        try{
            // Not insert in bulk_operations because it depends on post_info document
            // and when this fails, the other MUST also to fail
            await mongodb.insertOne("post_info", post_info_doc);
            await Promise.all([
                mongodb.insertOne("post_data", post_data_doc),
                mongodb.insertOne("post_text", post_text_doc),
                mongodb.insertOne("post_raw", post_raw_doc),
            ])
        }catch{/* Duplicate Error */}

        resolve()
    }).catch((err) => {})
}

function handleVoteOP(op_value){
    return new Promise(async (resolve) => {
        // Find account_info
        const account_info = await mongodb.findOneInCollection("account_info", {name : op_value.voter});
        if(!account_info){
            // Account does not exist --> check if banned. Else create one
            if(await mongodb.findOneInCollection("banned", {name : op_value.voter})){
                resolve();
                return;
            }

            // Not banned --> Create account and set profile information
            const _id = await mongodb.generateUnusedID("account_info");
            bulks_account_info.push({insertOne : {document : {_id : _id, name : op_value.voter}}});

            resolve();
            return;
        }

        // Find account_data --> When available the account was analyzed
        const account_data = await mongodb.findOneInCollection("account_data", {_id : account_info._id});
        if(!account_data){
            // Account is not analyzed --> just return
            resolve();
            return;
        }

        // Find post and then set it into
        const post_info = await mongodb.findOneInCollection("post_info", {author : op_value.author, permlink: op_value.permlink});
        if(post_info)
            bulks_post_data.push({ updateOne : {
                filter : {_id : post_info._id},
                update : {$addToSet : {votes : account_info._id}}
            }});

        resolve();
    }).catch((err) => {})
}

function handleCustomJson(op_value){
    return new Promise(async (resolve) => {
        if(op_value.id !== "config_hive_discover"){
            // Not interesting
            resolve();
            return;
        }

        const account = op_value.required_posting_auths[0];
        const json = JSON.parse(op_value.json);

        //  ** Ban Stuff **
        if(json.cmd === "ban"){
            if(!await mongodb.findOneInCollection("banned", {name : account})){
                // Enter into DB and check if
                await mongodb.insertOne("banned", {name : account});

                const account_info = await mongodb.findOneInCollection("account_info", {"name" : account});
                if(account_info){
                    // Got data about him --> delete everything
                    // 1. Find posts by him
                    let post_ids = [];
                    for await(const post of await mongodb.findManyInCollection("post_info", {author : account}, {_id : 1}))
                        post_ids.push(post._id);


                    // 2. Delete all
                    await Promise.all([
                        mongodb.deleteMany("account_info", {_id : account_info._id}), // account_info entry
                        mongodb.deleteMany("account_data", {_id : account_info._id}), // account_data entry
                        mongodb.updateMany("post_data", {votes : account_info._id}, {$pull : {votes : account_info._id}}), // votes entries
                        mongodb.deleteMany("post_info", {_id : {$in : post_ids}}), // post_info entry
                        mongodb.deleteMany("post_data", {_id : {$in : post_ids}}), // post_data entry
                        mongodb.deleteMany("post_text", {_id : {$in : post_ids}}), // post_text entry
                        mongodb.deleteMany("post_raw", {_id : {$in : post_ids}}), // post_raw entry
                    ]);

                }
            }
        }
        if(json.cmd === "unban")
            await mongodb.deleteMany("banned", {name : account});
        


        resolve();
    }).catch((err) => {})
}

function handleAccountUpdateOP(op_value){
    return new Promise(async (resolve) => {
        // Prepare account_profile
        let metadata;
        try{
            metadata = JSON.parse(op_value.json_metadata);
        }catch{resolve(); return; /* Nothing is there */}
        
        if(metadata.profile)
            metadata = metadata.profile

        let account_profile = {};
        if(metadata.location)
            account_profile.location = metadata.location;
        if(metadata.about)
            account_profile.about = metadata.about;
        if(metadata.name)
            account_profile.name = metadata.name;



        // Find account
        const account_info = await mongodb.findOneInCollection("account_info", {name : op_value.account});
        if(!account_info){
            // Check if banned
            if(await mongodb.findOneInCollection("banned", {name : op_value.account})){
                resolve();
                return;
            }

            // Not banned --> Create account and set profile information
            const _id = await mongodb.generateUnusedID("account_info");
            bulks_account_info.push({insertOne : {document : {_id : _id, name : op_value.account, profile : account_profile}}});
        } else {
            // Update profile_information
           // await mongodb.updateOne("account_info", {_id : account_info._id}, {$set : {profile : account_profile}})
           bulks_account_data.push({updateOne : {
               filter : {_id : account_info._id},
               update : {$set : {profile : account_profile}}
           }});
        }

        resolve();
    }).catch((err) => {})
}

//  *** Start/Main Functions ***
let currentBlockNum = -1;
async function getStartBlockNum(){
    const doc = await mongodb.findOneInCollection("stats", {tag : "CURRENT_BLOCK_NUM"});
    if(doc){
        // last blockNum is available
        currentBlockNum = doc.current_num;
    } else{
        // Nothing is available --> get current minus some buffers
        currentBlockNum = (await getCurrentBlockHeigth()) - 100;
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

    let corrupted_ids = new Set()  

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
    let tasks = [];
    try{
        const blockHeight = await getCurrentBlockHeigth().catch(err => {}); 
        if((currentBlockNum + 5) < blockHeight){
            // Some blocks available (+5 to have a buffer)
            let amount = Math.min((blockHeight - currentBlockNum), 50) // Set amount max to 50
            let requestIds = function (){
                // Return all block Ids which should be queried
                let l = [];
                for(let i = 0; i < amount; i++)
                    l.push(currentBlockNum + i)
                return l;
            }

            await getBlockOperations(requestIds()).then((apiResponse) => {
                // Iterate through over all blocks (apiResponse = [block1, block2, block3 ...])
                apiResponse = JSON.parse(apiResponse);
                for(let i = 0; i < apiResponse.length; i++){
                    currentBlockNum += 1

                    // Iterate through every operation in block (block = [op1, op2, op3 ...])
                    for(let k = 0; k < apiResponse[i].result.length; k ++){
                        const operation = apiResponse[i].result[k];
                        const op_name = operation.op[0], op_value = operation.op[1];

                        switch(op_name){
                            case "vote":
                                tasks.push(handleVoteOP(op_value))
                                break;
                            case "comment":
                                tasks.push(handleCommentOP(op_value))
                                break;
                            case "account_update":
                                tasks.push(handleAccountUpdateOP(op_value));
                                break
                            case "custom_json":
                                tasks.push(handleCustomJson(op_value))
                                break;
                        }
                    }
                    
                }
            }).catch(err => console.log("Error", err))

            tasks.push(mongodb.updateOne("stats", {tag : "CURRENT_BLOCK_NUM"}, {$set : {current_num : currentBlockNum}}));
            try{
                await Promise.all(tasks)
            }catch(err){console.log("Error on doing the tasks", err)}

            // Do updates
            try{
                if(bulks_account_data.length > 0){
                    await mongodb.performBulk("account_data", bulks_account_data);
                    bulks_account_data = [];
                }
                if(bulks_account_info.length > 0){
                    await mongodb.performBulk("account_info", bulks_account_info);
                    bulks_account_info = [];
                }
                if(bulks_post_info.length > 0){
                    await mongodb.performBulk("post_info", bulks_post_info);
                    bulks_post_info = [];
                }
                if(bulks_post_data.length > 0){
                    await mongodb.performBulk("post_data", bulks_post_data);
                    bulks_post_data = [];
                }
                if(bulks_post_text.length > 0){
                    await mongodb.performBulk("post_text", bulks_post_text);
                    bulks_post_text = [];
                }
            }catch{}
        } else {
            // Use time to repair Database
            await repairDatabase();
        }
    }catch{
        currentBlockNum -= 150; // buffer
        console.error("Something went wrong. Retry later again...");
    }

    // Rerun when new blocks are available (Every 3sec)
    setTimeout(main, 3000);
}

// Start everything
mongodb.logAppStart("chain-listener");
mongodb.connectToDB()
    .then(async ()=>{
        await repairDatabase();
        await getStartBlockNum();
        main();
    })
    .catch(err => {
      console.error(err);
    }) 
