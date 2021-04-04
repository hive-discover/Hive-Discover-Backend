const hivejs = require('@hivechain/hivejs')
const MarkdownIt = require('markdown-it')
const md = new MarkdownIt();
const HTMLParser = require('node-html-parser');

const hiveSigner = require('hivesigner')

function processBody(post_obj){
    return new Promise((resolve, reject) => {
        if(post_obj.body){
            // Convert markdown to html
            post_obj.body = md.render(post_obj.body);
            post_obj.json_metadata.format = "html";
            

            // Parse html body
            let root = HTMLParser.parse(post_obj.body)       
            const imgs = root.querySelectorAll('img')

            // Get more images
            for(let i = 0; i < imgs.length; i ++)
            {    
                let src = imgs[i].attrs.src
                if(!src in post_obj.json_metadata.image)
                    post_obj.json_metadata.image.push(elem)
            }

            // Reparse to get ONLY text
            root = HTMLParser.parse(root.text)
            post_obj.body = root.text
            if(post_obj.body.length > 450)
                post_obj.body = post_obj.body.slice(0, 500);
            post_obj.body += "...";

            post_obj.body = post_obj.body.replace(/\b((?:[a-z][\w-]+:(?:\/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}\/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’]))/g, "");
        }
        resolve(post_obj);
    });
}

function getContent(author, permlink){
    let contentgetter = new Promise((resolve, reject) => {
        hivejs.api.getContent(author, permlink, (err, result) => {
            if(err){
                resolve({});
                return;
            }

            let metadata = JSON.parse(result.json_metadata)
            if("image" in metadata == false)
                metadata.image = []
            if("tags" in metadata == false)
                metadata.tags = []

            resolve({
                author : result.author,
                permlink : result.permlink,
                url : result.url,
                title : result.title,
                body : result.body,
                created : result.created,
                json_metadata : {
                    tags : metadata.tags,
                    image : metadata.image,
                    app : metadata.app,
                    format : metadata.format
                    }
                });
            });
    })

    return contentgetter
        .then(post_obj => processBody(post_obj))
        .catch(null)
}


function checkAccessToken(username, access_token){
    const client = new hiveSigner.Client({ app: 'action-chain', scope: ['login'], accessToken : access_token});

    return new Promise((resolve, reject) => {
        client.me(function (err, result) {
            if(result && result.user == username)
                resolve(true)           
            else
                resolve(false);
        });
    });
}


function getAccounts(accounts){
    return new Promise(resolve => {
        hivejs.api.getAccounts(accounts, function(err, result) {
            if(err || !result || result.length == 0)
                resolve([]);
            else {
                accs = []
                
                result.forEach(elem => {
                    obj = {name : elem.name}
                    try{
                        obj.json_metadata = JSON.parse(elem.json_metadata)  
                    } catch {}
                    accs.push(obj);
                });

                resolve(accs);
            }               
          });
    })   
}


module.exports = { getContent, checkAccessToken, getAccounts };