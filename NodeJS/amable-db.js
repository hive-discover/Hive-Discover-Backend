var request = require('request');

var SERVER_SETTINGS = {
    'url' : ""
}

function connectToDB(url){
    // Set url in settings
    SERVER_SETTINGS.url = url;

    var options = {
        'method': 'GET',
        'url': SERVER_SETTINGS.url + '/',
        'headers': {}
    };

    // Test Connection
    return new Promise( resolve => {
        request(options, (error, response) => {
            if (error) 
                resolve(false); // Network Error
            else 
                resolve(true); // Success
        });
    });
}

//  *** SELECT ***
function select(query, counter = 0, lastError = null){
    var options = {
        'method': 'POST',
        'url': SERVER_SETTINGS.url + '/select',
        'headers': {
            'Content-Type': 'application/json'
        },
        'body' : JSON.stringify(query)
    }

    return new Promise(resolve => {
            // Send to Server
            request(options, async (error, response) => { 
                if(counter > 7) // Fully failed
                    throw Error(lastError);

                if (error) {
                    // Check if an error raised
                    resolve(await select(query, counter + 1, error));
                } else if(response) // Resolve Response
                    resolve(JSON.parse(response.body)); });
        }).then(value => {
            // Process response
            if(value.status !== "ok")
                throw Error("Status is not OK");
        
            // Return Cursor Object
            return {'count' : value.count, 'cursor_uuid' : value.cursor_uuid};
        }).catch(error => {
            // Something went wrong: Cannot connect, JSON Parse Failed...
            return null;
        });
}

function bulk(bulk_ops, counter = 0, lastError = null){
    var options = {
        'method': 'POST',
        'url': SERVER_SETTINGS.url + '/bulk',
        'headers': {
            'Content-Type': 'application/json'
        },
        'body' : JSON.stringify(bulk_ops)
    }

    return new Promise(resolve => {
            // Send to Server
            request(options, async (error, response) => { 
                if(counter > 7) // Fully failed
                    throw Error(lastError);

                if (error) {
                    // Check if an error raised
                    await bulk(bulk_ops, counter + 1, error);
                    resolve(); return;
                } else if(response) // Resolve Response
                    resolve(JSON.parse(response.body)); });
        }).then(value => {
            // Process response
            if(value.status !== "ok")
                throw Error("Status is not OK");
        
            // Return bulk Object
            return value.bulk;
        }).catch(error => {
            // Something went wrong: Cannot connect, JSON Parse Failed...
            return null;
        });
}

async function* getCursorItems(cursor){
    var options = {
        'method': 'GET',
        'url': SERVER_SETTINGS.url + '/cursor?cursor_uuid=' + cursor.cursor_uuid,
        'headers': {}
    };

    let finished = false;
    let lastTask = null;
    let lastResponse = null;

    const getFunc = (options, counter = 0, lastError = null) => {
        if(counter > 7)
            throw Error(lastError);
        
        // Make request
        return new Promise(resolve => {
            request(options, (error, response) => {
                if (error) 
                    resolve(getFunc(options, counter + 1, error));
                else  {
                    if(response.statusCode == 200){
                        // Resolve response body as an Object
                        resolve(JSON.parse(response.body));
                        return;
                    }

                    // Error (like Bad Gadway 502)
                    resolve(getFunc(options, counter + 1, response));
                }
              });
        });
        
    }

    while(!finished){
        // Await last GET-task
        if(lastTask) { lastResponse = await lastTask; }

        // Restart Task
        lastTask = getFunc(options);

        // Process last Response
        if(lastResponse){
            if(lastResponse.status !== "ok")
                throw Error("Status is not OK");
            
            // Yield all docs
            for(let [index, score, item] of lastResponse.items)
                yield {'index' : index, 'score' : score, 'item' : item};

            // Check if finished
            finished = lastResponse.finished;
        }
    }

    
}


async function testAll(){
    if(!(await connectToDB("http://api.hive-discover.tech:3399")))
        throw Error("Failed to Connect to DB");

    const cursor = await select({
        "query": {
          "#limit": 50000,
          "#similar": {
            "fieldName": "categories",
            "k": 100,
            "value": [
                0,5,7,9,4,2,6,8,7,8,9,2,1,2,3,5,6,9,7,8,5,2,1,74,9,7,9,
                0,5,7,9,4,2,6,8,7,8,9,2,1,2,3,5,6,9,7,8,5,2,1,74,9,7,9
            ]
          }
        },
        "collection": "post_cats"
    });
    console.log(cursor);
    
    for await ({item} of getCursorItems(cursor))
        console.log(item)
}

//testAll();

module.exports = { connectToDB, select, bulk, getCursorItems };