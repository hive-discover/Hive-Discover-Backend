console.log(require('dotenv').config({ path: './NodeJS/docker_variables.env' }))
const hivejs = require('@hivechain/hivejs')

const mongodb = require('./database.js')
const config = require('./config')

//  *** Correct Timestamps ***
async function correctTimestamps(batch_size=1024){
    let bulk_update = [], bulk_task = async () => {}, check_task = async () => {};
    const corrector = (_id, author, permlink, prev_timestamp) => {
        hivejs.api.setOptions({ url: config.getRandomNode() });
        return new Promise(resolve => {
            hivejs.api.getContent(author, permlink, (err, result) => {
                if(result){
                    // Update timestamp (is universal)
                    const timestamp = new Date(Date.parse(result.created));
                    if(timestamp && (prev_timestamp.getDay() !== timestamp.getDay() || prev_timestamp.getMonth() !== timestamp.getMonth())){
                        bulk_update.push({updateOne: {
                            filter : {_id : _id},
                            update : {$set : {timestamp : timestamp}}
                        }})
                    }           
                }
                resolve();
            });
        })      
    }
    
    let current_doc = 0, bulk_operations = 0;

    let d = new Date(year=2021, month=3, date=10)
    let posts = await (await mongodb.findManyInCollection("post_info", {timestamp : {$gt : d}})).toArray();
    let tasks = [];
    for(let i=0; i < posts.length; i++){
        const post_info = posts[i];
        tasks.push(corrector(post_info._id, post_info.author, post_info.permlink, post_info.timestamp));

        if(tasks.length > 25){
            await Promise.all(tasks);
            tasks = [];
        }
        

        // Perform Bulk Operation+
        if(bulk_update.length >= 10 || i === posts.length - 1){
            await bulk_task;
            bulk_task = Promise.all([
                mongodb.performBulk("post_info", [...bulk_update]),
                mongodb.performBulk("post_text", [...bulk_update]),
                mongodb.performBulk("post_data", [...bulk_update]),
                mongodb.performBulk("post_raw",  [...bulk_update])
            ]);
            bulk_update = [];
            bulk_operations += 1;
            console.log(bulk_operations);
        }
    }

    return;

    // Iterate through every document
    let total_documents = await mongodb.countDocumentsInCollection("post_info", {})
    while(current_doc <= total_documents){
        const cursor = (await mongodb.findManyInCollection("post_info", {})).sort({timestamp : -1}).skip(current_doc).limit(batch_size);
        current_doc += batch_size;

        let tasks = [];
        await cursor.forEach(post_info => {
            tasks.push(corrector(post_info._id, post_info.author, post_info.permlink, post_info.timestamp));
        });
        
        // Wait for finish last tasks
        await check_task;
        check_task = Promise.all([...tasks]);
        
        // Perform Bulk Operation+
        if(bulk_update.length >= 500 || current_doc >= total_documents){
            await bulk_task;
            bulk_task = Promise.all([
                mongodb.performBulk("post_info", [...bulk_update]),
                mongodb.performBulk("post_text", [...bulk_update]),
                mongodb.performBulk("post_data", [...bulk_update]),
                mongodb.performBulk("post_raw",  [...bulk_update])
            ]);
            bulk_update = [];
            console.log(current_doc);
            bulk_operations += 1;
        }
    }
    console.log("Finished. Total made: " + bulk_operations.toString())
}


mongodb.connectToDB()
    .then(async ()=> {
        await correctTimestamps();
    })