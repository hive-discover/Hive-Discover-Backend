const HTMLParser = require('node-html-parser');
const MarkdownIt = require('markdown-it')
const md = new MarkdownIt();

const mongodb = require('./../database.js')
const config = require('./../config')


//  *** Handler Operations ***
const commentOperations = async (op_values) => {
    const handler_func = (async (comment) => {
        if(comment.parent_author !== "") return; // Is a Comment

        // Get later unused id and check if it exists
        const getUnusedID_task = mongodb.generateUnusedID("post_info");

        // Check if banned (post or user) OR if it's exists
        if( await mongodb.findOneInCollection("banned", {author : comment.author, permlink: comment.permlink}) || 
            await mongodb.findOneInCollection("banned", {name : comment.author}) ||
            await mongodb.findOneInCollection("post_info", {author : comment.author, permlink: comment.permlink})
        ) {
            // Is banned / already exists
            return;
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
        config.BANNED_WORDS.forEach((item)=>{
            if(
                comment.body.indexOf(item) >= 0 || 
                comment.json_metadata.tags.includes(item) >= 0 ||
                comment.title.indexOf(item) >= 0
            ){
                // Not enter
                return;
            }
        });

        // Parse body and extract more images
        let html_body = md.render(comment.body);
        let root = HTMLParser.parse(html_body);  
        const imgs = root.querySelectorAll('img')
        for(let i = 0; i < imgs.length; i ++)
        {    
            let src = imgs[i].attrs.src
            if(src && !(src in comment.json_metadata.image))
            comment.json_metadata.image.push(src)
        }

        // Reparse to only get text
        root = HTMLParser.parse(root.text);
        comment.body = root.text;   
        const plain_body = comment.body;
        comment.body = config.slugifyText(comment.body); // replaceAll non-latin
        comment.title = config.slugifyText(comment.title); // replaceAll non-latin
        comment.json_metadata.tags = config.slugifyText(comment.json_metadata.tags); // replaceAll non-latin

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
        const post_info_doc = {_id : post_id, author : comment.author, permlink : comment.permlink, timestamp : comment.timestamp};
        const post_text_doc = {_id : post_id, title : comment.title, body : comment.body, tag_str : comment.json_metadata.tags, timestamp : comment.timestamp}
        const post_data_doc = {_id : post_id, categories : null, lang : null, timestamp : comment.timestamp}
        raw_post.json_metadata = comment.json_metadata;
        const post_raw_doc = {_id : post_id, timestamp : comment.timestamp, raw : raw_post, plain : {body : plain_body}}

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
    });

    // Start all tasks
    let handler_tasks = [];
    op_values.forEach(comment => {
        handler_tasks.push(handler_func(comment).catch(err => console.error("Error while handling Comment: ", err)))
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
            }
                
        }
    });

    // Start all tasks
    let handler_tasks = [];
    op_values.forEach(async vote => {
        handler_tasks.push(handler_func(vote).catch(err => console.error("Error while handling Vote: ", err)))
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
    });

    // Start all tasks
    let handler_tasks = [];
    op_values.forEach(async value => {
        handler_tasks.push(handler_func(value).catch(err => console.error("Error while handling AccountUpdates: ", err)))
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
            await mongodb.insertOne("account_data", {_id : account_id, accept : {timestamp : new Date(Date.now()), trx_id : trx}}).catch(err => {/* Not interesting */});
        }

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
    });

    // Start all tasks
    let handler_tasks = [];
    op_values.forEach(async (value, index) => {
        handler_tasks.push(handler_func(value, trx_ids[index]).catch(err => console.error("Error while handling CustomJSON: ", err)))
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

module.exports = {onBlock};
