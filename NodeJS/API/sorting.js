const config = require("../config.js")
const mongodb = require('./database.js')

var similarity = require( 'compute-cosine-similarity' );


async function sortPersonalized(post_ids, account_name, account_id){
    let own_categories = [], post_categories =[];

    // Get categories from his votes
    let catsOfHisVotes = new Promise(async (resolve) => {
        const cursor = await mongodb.findManyInCollection("post_data", {votes : account_id}, {projection : {_id : 1, categories : 1}});
        for await (const post of cursor){
            if(post.categories && Array.isArray(post.categories) && post.categories.length == config.CATEGORIES.length){
                own_categories.push(post)
            }
        }

        resolve();
    });

    // Get categories from his posts
    let catsOfHisPosts = new Promise(async (resolve) => {
        // Find his Ids
        let hisPostIds = [];
        let cursor = await mongodb.findManyInCollection("post_info", {author : account_name}, {projection : {_id : 1}});
        for await (const post of cursor)
            hisPostIds.push(post._id);

        // Enter ids
        cursor = await mongodb.findManyInCollection("post_data", {_id : {$in : hisPostIds}}, {projection : {_id : 1, categories : 1}});
        for await (const post of cursor){
            if(post.categories && Array.isArray(post.categories) && post.categories.length == config.CATEGORIES.length){
                own_categories.push(post)
            }
        }
 
        resolve();
    });

    // Get categories from the post_ids
    let catsOfSPosts = new Promise(async (resolve) => {
        const cursor = await mongodb.findManyInCollection("post_data", {_id : {$in : post_ids}}, {projection : {_id : 1, categories : 1}});
        for await (const post of cursor){
            if(post.categories && Array.isArray(post.categories) && post.categories.length == config.CATEGORIES.length){
                post_categories.push(post)
            }
        }

        resolve();
    });

    await Promise.all([catsOfHisVotes, catsOfHisPosts, catsOfSPosts]);

    // Calc similarities
    let scores = [];
    post_categories.forEach((s_post) => {
        let item = {_id : s_post._id, score : 0};
        
        own_categories.forEach((own_post) => {      
            item.score += Math.abs(similarity(own_post.categories, s_post.categories));
        });

        scores.push(item);
    });

    // Sort by score (highest score at 0; lowest score at the end)
    scores = scores.sort((a, b) => {
        return b.score - a.score;
    });

    // Extract only Ids
    scores = scores.map((item) => item._id);
    return scores;
}

module.exports = {sortPersonalized};

