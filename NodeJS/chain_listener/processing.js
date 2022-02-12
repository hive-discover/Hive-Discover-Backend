const HTMLParser = require('node-html-parser');
const MarkdownIt = require('markdown-it')
const md = new MarkdownIt();
const logging = require('./../logging.js')
const hivejs_lib = require('@hivechain/hivejs')

const mongodb = require('./../database.js')
const config = require('./../config')


//  *** Handler Operations ***
const commentOperations = async (op_values) => {
    const handler_func = (async (comment) => {
        
        
        // Check if Comment
        if(comment.parent_author !== "") { 
            // Is a Comment ==> return but firstly check if it is a reply to HiveStockImage-Community
            if(comment.json_metadata.includes("hive-118554")) {        
                if(comment.body.includes("!update-stock-image-tags")){
                    // Try to find the stock-image-post
                    const post_info = await mongodb.findOneInCollection("post_info", {author : comment.parent_author, permlink : comment.parent_permlink}, "images");
                    if(!post_info) return; // No post found
                    // post_info.author === comment.parent_author

                    // Check if User is allowed to change the hashtags
                    //  Only the original author or the MOD/ADMIN of the community is allowed to do that
                    const allowed_accounts = [post_info.author, "hive-118554", "minismallholding", "crosheille", "kattycrochet"];
                    if(!allowed_accounts.includes(comment.author)) return; // User is not allowed

                    // Get Tags and Update the stock-image-post
                    comment.body = comment.body.replace("\n", " ");
                    let image_tags = comment.body.split(' ').filter(v=> v.startsWith('#'))
                    image_tags = image_tags.map(v=> v.substring(1));
                    image_tags = image_tags.join(' ');

                    await mongodb.updateOne("post_text", {_id : post_info._id}, {$set : {text : image_tags, doc_vectors : null, updated : true}}, true, "images");
                    logging.writeData(logging.app_names.chain_listener, {"msg" : "Updates Stock Image Keywords", "info" : {"post" : post_info._id}});
                } else {
                    // Is a simple reply to a StockImage Post, no update-comment
                    // Insert comment in collection
                    const comment_id = await mongodb.generateUnusedID("post_replies", "images");
                    await mongodb.insertOne("post_replies", {
                        _id : comment_id,
                        author : comment.author, 
                        permlink : comment.permlink,
                        text : comment.body
                    }, "images");

                    // Push comment_id to post_info
                    await mongodb.updateOne("post_info", {author : comment.parent_author, permlink : comment.parent_permlink}, {$addToSet : {replies : comment_id}}, false, "images");
                }
            }

            return; // Return anyways because it is no actual post
        }

        // Get later unused id and check if it exists
        let getUnusedID_task = mongodb.generateUnusedID("post_info");

        // Check if banned (post or user)
        if( await mongodb.findOneInCollection("banned", {author : comment.author, permlink: comment.permlink}) || 
            await mongodb.findOneInCollection("banned", {name : comment.author})
        ) {
            // Is banned
            return;
        }

        // Check if post exists
        const post_info = await mongodb.findOneInCollection("post_info", {author : comment.author, permlink: comment.permlink})
        if(post_info){
            // Post Already exists ==> Download the full-changed-post from the blockchain
            comment = await new Promise((resolve, reject) => {
                hivejs_lib.api.getContent(comment.author, comment.permlink, (err, result) => {
                    if(result){
                        // Got a comment
                        resolve(result);
                        return;
                    }

                    // Something failed
                    reject(err);
                });
            }).catch(err => {
                // Log error
                console.log("Error getting Content from changed content: ", err);
                logging.writeData(logging.app_names.chain_listener, {"msg" : "New Content cannot get downloaded", "info" : {"post" : post_info._id, "err" : err}}, 1);
                return null;
            });

            if(!comment) return; // No comment found, just let the change unprocessed

            // Delete post from hive-discover DB
            await Promise.all([
                mongodb.deleteMany("post_info", {_id : post_info._id}),
                mongodb.deleteMany("post_text", {_id : post_info._id}),
                mongodb.deleteMany("post_data", {_id : post_info._id}),
                mongodb.deleteMany("post_raw", {_id : post_info._id})
            ]);

            // Invoke the id task
            getUnusedID_task = new Promise(resolve => {resolve(post_info._id)});
            logging.writeData(logging.app_names.chain_listener, {"msg" : "One General Post got updated", "info" : {"post" : post_info._id}});
        }

        // Start preparing the Post
        try{
            comment.json_metadata = JSON.parse(comment.json_metadata)
        } catch {
            // JSON Parse error --> set to {} because it is usually '' then
            comment.json_metadata = {}
        }
        
        // Parse Tags and Images
        if(!comment.json_metadata.tags) 
            comment.json_metadata.tags = [];
        if(!comment.json_metadata.image) 
            comment.json_metadata.image = [];
        let raw_post = {...comment};

        if(Array.isArray(comment.json_metadata.tags))
            comment.json_metadata.tags = comment.json_metadata.tags.join(" ");
        if(!Array.isArray(comment.json_metadata.image))
            comment.json_metadata.image = [comment.json_metadata.image];

        // Check banned Words
        let stop_working = false;
        config.BANNED_WORDS.forEach((item)=>{
            if(
                comment.body.includes(item) || 
                comment.json_metadata.tags.includes(item) ||
                comment.title.includes(item) 
            ){
                // Not enter
                stop_working = true;
            }
        });
        if(stop_working) return;

        // Parse body and extract more images
        let html_body = md.render(comment.body);
        let root = HTMLParser.parse(html_body);  
        const imgs = root.querySelectorAll('img')
        for(let i = 0; i < imgs.length; i ++)
        {    
            let src = imgs[i].attrs.src
            if(src && !comment.json_metadata.image.includes(src))
                comment.json_metadata.image.push(src)
        }

        // Reparse to only get text
        root = HTMLParser.parse(root.text);
        comment.body = root.text;   
        comment.body = comment.body.replace(/\n/g, " \n ");
        const plain_body = comment.body;
        if(comment.body.split(' ').length < 10) {
            // Too low words
            return;
        }

        if(comment.timestamp)
            comment.timestamp = new Date(Date.parse(comment.timestamp));
        else 
            comment.timestamp = new Date(Date.now());

        // Prepare documents. Timestamp just now becuase comment does not have it but because it is the latest block it matches it (nearly)
        const post_id = await getUnusedID_task;
        const post_info_doc = {_id : post_id, author : comment.author, permlink : comment.permlink, parent_permlink : comment.parent_permlink, timestamp : comment.timestamp};
        const post_text_doc = {_id : post_id, title : comment.title, body : comment.body, tag_str : comment.json_metadata.tags, timestamp : comment.timestamp}
        const post_data_doc = {_id : post_id, categories : null, lang : null, doc_vectors : null, timestamp : comment.timestamp}
        raw_post.json_metadata = comment.json_metadata;
        const post_raw_doc = {_id : post_id, timestamp : comment.timestamp, raw : raw_post, plain : {body : plain_body}}

        // Check if post is a stock-image
        if(
            comment.json_metadata.tags.includes("hivestockimages") ||
            comment.json_metadata.tags.includes("hive-118554") ||
            comment.parent_permlink === "hive-118554" ||
            comment.parent_permlink === "hivestockimages"
        ){
            if(await mongodb.findOneInCollection("muted", {_id : comment.author}, "images")){
                // Is a muted account ==> return the whole process of entering it
                return;
            }

            let stock_post_id = await mongodb.generateUnusedID("post_info", "images");

            // Check if it got updated
            const img_post_info = await mongodb.findOneInCollection("post_info", {author : comment.author, permlink: comment.permlink}, "images");
            if(img_post_info){
                // Post Already exists ==> Delete post from images DB
                await Promise.all([
                    mongodb.deleteMany("post_info", {_id : img_post_info._id}, "images"),
                    mongodb.deleteMany("post_text", {_id : img_post_info._id}, "images"),
                    mongodb.deleteMany("post_data", {_id : img_post_info._id}, "images"),
                ]);

                // Invoke the id
                stock_post_id = img_post_info._id;
                logging.writeData(logging.app_names.chain_listener, {"msg" : "One Stock Image Post got updated", "info" : {"post" : stock_post_id}});
            }

            // Prepare Text, extract all words beginning with a hashtag and then remove the hashtag
            let image_tags = comment.body.split(' ').filter(v=> v.startsWith('#'))
            image_tags = image_tags.map(v=> v.substring(1));
            image_tags = image_tags.join(' ');

            // Insert in images.post_info
            await mongodb.insertOne("post_info", {
                _id : stock_post_id,
                author : comment.author,
                permlink : comment.permlink,
                timestamp : comment.timestamp,
                images : comment.json_metadata.image,
                title : comment.title              
            }, "images");

            // Insert int post_text
            await mongodb.insertOne("post_text", {
                _id : stock_post_id,
                text : image_tags,
                doc_vectors : null
            }, "images");

            logging.writeData(logging.app_names.chain_listener, {"msg" : "Insert new Stock Image Post", "info" : {"post" : stock_post_id}});
        }

        try{
            // Not insert in bulk_operations because it depends on post_info document
            // and when this fails, the other MUST also to fail
            await mongodb.insertOne("post_info", post_info_doc);
            await Promise.all([
                mongodb.insertOne("post_data", post_data_doc),
                mongodb.insertOne("post_text", post_text_doc),
                mongodb.insertOne("post_raw", post_raw_doc),
            ]);
            logging.writeData(logging.app_names.chain_listener, {"msg" : "Inserted a new Post", "info" : {"post" : post_id}});
        }catch{/* Duplicate Error */}
    });

    // Start all tasks
    let handler_tasks = [];
    op_values.forEach(comment => {
        handler_tasks.push(handler_func(comment).catch(err => {
            console.error("Error while handling Comment: ", err);
            logging.writeData(logging.app_names.chain_listener, {"msg" : "Error Handling Comments", "info" : {"err" : err}});
        }));
    });

    // Finish up
    if(handler_tasks.length > 0)
        await Promise.all(handler_tasks);
}

const voteOperations = async (op_values) => {
    let bulks_post_data = [];
    const handler_func = (async (vote) => {
        // Find account_info
        const account_info = await mongodb.findOneInCollection("account_info", {name : vote.voter});
        let account_id = -1;
        if(!account_info){
            // Account does not exist --> check if banned. Else create one
            if(await mongodb.findOneInCollection("banned", {name : vote.voter})){
                resolve();
                return;
            }

            // Not banned --> Create account
            account_id = await mongodb.generateUnusedID("account_info");
            await mongodb.insertOne("account_info", {_id : account_id, name : vote.voter});
            logging.writeData(logging.app_names.chain_listener, {"msg" : "Created new account", "info" : {"username" : vote.voter}});
        } else {
            // We got the account
            account_id = account_info._id;
        }

        if(account_id > 0){
            // Find post and then set it into
            const post_info = await mongodb.findOneInCollection("post_info", {author : vote.author, permlink: vote.permlink});
            if(post_info){
                bulks_post_data.push({ updateOne : {
                    filter : {_id : post_info._id},
                    update : {$addToSet : {votes : account_id}}
                }});
                logging.writeData(logging.app_names.chain_listener, {"msg" : "Added Vote to Post", "info" : {"post" : post_info._id, "account" : account_id}});
            } else {
                logging.writeData(logging.app_names.chain_listener, {"msg" : "Cannot Find Post to add that Vote (maybe to old)", "info" : {"author" : vote.author, "permlink" : vote.permlink}});
            }
                
        }
    });

    // Start all tasks
    let handler_tasks = [];
    op_values.forEach(async vote => {
        handler_tasks.push(handler_func(vote).catch(err => {
            console.error("Error while handling Vote: ", err);
            logging.writeData(logging.app_names.chain_listener, {"msg" : "Error Handling Votes", "info" : {"err" : err}}, 1);
        }));
    });

    // Finish up
    if(handler_tasks.length > 0)
        await Promise.all(handler_tasks);
    if(bulks_post_data.length > 0)
        await mongodb.performBulk("post_data", bulks_post_data).catch(err => console.error("Error while entering Votes: ", err));
}

const accUpdateOperations = async (op_values) => {
    let bulks_account_info = [];
    const handler_func = (async (op_value) => {
        // Prepare account_profile
        let metadata;
        try{
            metadata = JSON.parse(op_value.json_metadata);
        }catch{ return; /* Nothing is there */}
        
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
            if(await mongodb.findOneInCollection("banned", {name : op_value.account})) return;

            // Not banned --> Create account and set profile information
            const _id = await mongodb.generateUnusedID("account_info");
            bulks_account_info.push({insertOne : {document : {_id : _id, name : op_value.account, profile : account_profile}}});
        } else {
            // Update profile_information
           bulks_account_info.push({updateOne : {
               filter : {_id : account_info._id},
               update : {$set : {profile : account_profile}}
           }});
        }
        logging.writeData(logging.app_names.chain_listener, {"msg" : "Account Update", "info" : {"username" : op_value.account}});
    });

    // Start all tasks
    let handler_tasks = [];
    op_values.forEach(async value => {
        handler_tasks.push(handler_func(value).catch(err => {
            console.error("Error while handling AccountUpdates: ", err);
            logging.writeData(logging.app_names.chain_listener, {"msg" : "Error handling AccountUpdate", "info" : {"err" : err}}, 1);
        }));
    });

    // Finish up
    if(handler_tasks.length > 0)
        await Promise.all(handler_tasks);
    if(bulks_account_info.length > 0)
        await mongodb.performBulk("account_info", bulks_account_info).catch(err => console.error("Error while entering AccountUpdates: ", err));
}

const customJSONOperations = async (op_values, trx_ids) => {
    const handler_func = (async (op_value, trx) => {
        if(op_value.id !== "config_hive_discover")  return; // Not interesting

        const account = op_value.required_posting_auths[0];
        const json = JSON.parse(op_value.json);

        //  ** Accept Datapolicy Stuff **
        if(json.cmd === "accept"){
            // Maybe delete banned entry
            await mongodb.deleteMany("banned", {name : account});

            // Check if account is available, else create one
            const account_info = await mongodb.findOneInCollection("account_info", {name : account});
            let account_id = -1;
            if(!account_info){
                account_id = await mongodb.generateUnusedID("account_info");
                await mongodb.insertOne("account_info", {_id : account_id, name : account});
            }else {
                // We've got the account
                account_id = account_info._id;
            }

            // Enter into account_data with a link to this transaction
            await mongodb.insertOne("account_data", {_id : account_id, accept : {timestamp : new Date(Date.now()), trx_id : trx}})
            .then(() => {
                // Success ==> Log
                logging.writeData(logging.app_names.chain_listener, {"msg" : "Inserted successfully into account_data", "info" : {"username" : account, "acc_id" : account_id}});
            })
            .catch(err => {
                // Failed
                logging.writeData(logging.app_names.chain_listener, {"msg" : "Cannot Insert into account_data", "info" : {"err" : err, "username" : account, "acc_id" : account_id}}, 1);
            });
            
        }

        //  ** Ban Stuff **
        if(json.cmd === "ban"){
            if(!await mongodb.findOneInCollection("banned", {name : account})){
                // Enter into DB and check if
                await mongodb.insertOne("banned", {name : account});
                logging.writeData(logging.app_names.chain_listener, {"msg" : "User banned", "info" : {"username" : account}});

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
        if(json.cmd === "unban"){
            await mongodb.deleteMany("banned", {name : account});
            logging.writeData(logging.app_names.chain_listener, {"msg" : "User unbanned", "info" : {"username" : account}});
        }
    });

    // Start all tasks
    let handler_tasks = [];
    op_values.forEach(async (value, index) => {
        handler_tasks.push(handler_func(value, trx_ids[index]).catch(err => {
            console.error("Error while handling CustomJSON: ", err);
            logging.writeData(logging.app_names.chain_listener, {"msg" : "Error handling CustomJsons", "info" : {"err" : err}}, 1);
        }));
    });

    // Finish up
    if(handler_tasks.length > 0)
        await Promise.all(handler_tasks);
}



const filterOperations = (block_operations) => {
    filtered = {
        comments : [],
        votes : [],
        acc_updates : [],
        custom_jsons : {
            values : [],
            trx_ids : []
        }
    };

    // Go through every operation and filter
    block_operations.forEach(operation => {
        const op_name = operation.op[0], op_value = operation.op[1], trx_id = operation.trx_id;
        
        switch(op_name){
            case "vote":
                filtered.votes.push(op_value);
                break;
            case "comment":
                filtered.comments.push(op_value);
                break;
            case "account_update":
                filtered.acc_updates.push(op_value);
                break
            case "custom_json":
                filtered.custom_jsons.values.push(op_value);
                filtered.custom_jsons.trx_ids.push(trx_id);
                break;
        }        
    })

    return filtered;
}

const onBlock = async (block) => {
    filtered_operations = filterOperations(block.result);

    // Do all things in parralel, because every account just does one thing per block
    await Promise.all([
        commentOperations(filtered_operations.comments).catch(err => console.error("Error while working on Comments: ", err)),
        accUpdateOperations(filtered_operations.acc_updates).catch(err => console.error("Error while working on accUpdates: ", err)),
        customJSONOperations(filtered_operations.custom_jsons.values, filtered_operations.custom_jsons.trx_ids).catch(err => console.error("Error while working on CustomJSONs: ", err)),
        voteOperations(filtered_operations.votes).catch(err => console.error("Error while working on Votes: ", err))
    ]);
};

module.exports = {onBlock, commentOperations};
