// First step: Loading .env
try{
    console.log(require('dotenv').config({ path: './NodeJS/docker_variables.env' }));
    console.log(require('dotenv').config({ path: './docker_variables.env' }));
}catch{
    try{
        
    }catch{
        console.error("Cannot load envs!");
    }
}

const PROCESS_ARGS = process.argv.slice(2);

if(PROCESS_ARGS.length === 0){
    console.log("please provide a start argument. Enter --help to get more information...")
} else {
    // Start
    console.log("starting: " + PROCESS_ARGS[0])
    switch(PROCESS_ARGS[0]){
        case "--help":
            console.log(" Informations are available: ")
            console.log("--help: Get all information")
            console.log("--api: Start the API Process")
            break;
        case "--api":
            runner = require("./API/app.js")
            break;
        case "--analyzer":
            runner = require("./acc_analyzer/analyzer.js")
            break;
        case "--chainlistener":
            runner = require("./chain_listener/listener.js")
            break;
    }
}