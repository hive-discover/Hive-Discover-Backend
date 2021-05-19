#ifndef NMSLIB_WORKER_H
#define NMSLIB_WORKER_H

#include "hnswlib/hnswlib.h"

using namespace boost::property_tree;

/// <summary>
/// Method to create the Post-Index with all Posts within the last 10 days
/// </summary>
/// <param name="client">MongoCxx-Driver Client. This object is not thread-safe! Do not run this Method in anotehr thread than the client is created!</param>
/// <returns>Calculated Knn-Index</returns>
hnswlib::AlgorithmInterface<float>* createPostIndex(mongocxx::v_noabi::pool::entry client);

/// <summary>
/// Get similar Posts like the ones given
/// </summary>
/// <param name="posts">List categories from the posts</param>
/// <param name="k">Count of Neighbours</param>
/// <returns>List of similar Ids per Posts</returns>
std::vector<std::vector<int>> findSimilarPostsByCategory(std::vector<std::vector<float>> posts, const size_t k);

/// <summary>
/// Get an overview of the used langs inside the Posts. Add all lang-scores together and caluclate Percentages.
/// Every lang over 15% is added to accLangs
/// </summary>
/// <param name="postIds">Which ids should be processed?</param>
/// <param name="accLangs">Where should the Langs be inserted?</param>
/// <param name="pool">MongoCxx-Driver Pool (Because of Thread-Safetyness)</param>
/// <returns>std::Thread Object</returns>
std::thread getLangsFromIds(const std::vector<int>& postIds, bsoncxx::builder::basic::array& accLangs, mongocxx::pool& pool);

/// <summary>
/// Find all Activities by an Account: Ids of liked and self-written Posts
/// </summary>
/// <param name="accountId">MongoDB _id of account (to find it in the DB)</param>
/// <param name="accountName">Username of the account</param>
/// <param name="accActivities">Pointer to the Vector where the Ids should be inserted</param>
/// <param name="pool">MongoCxx-Driver Pool (Because of Thread-Safetyness)</param>
void getActivitiesFromAccount(const int accountId, const std::string& accountName, std::vector<int>* accActivities, mongocxx::pool& pool);


// PUBLIC AREA

/// <summary>
/// Endless Thread to periodically create a Post-Index
/// </summary>
/// <param name="parameter">std::pair of the MongoCxx-Pool (Thread-Safety) and a bool</param>
void manageIndex(std::pair<mongocxx::pool&, bool> parameter);

/// <summary>
/// Generate a Feed based on the Account's activities (Posting/Voting). Also check whether the recommended Posts
/// are written in the same Language as Posts he liked or wrote by himself.
/// </summary>
/// <param name="accountId">MongoDB _id of account (to find it in the DB)</param>
/// <param name="accountName">Username of the account</param>
/// <param name="amount">How many Posts do you want?</param>
/// <param name="pool">MongoCxx-Driver Pool (Because of Thread-Safetyness)</param>
/// <param name="abstractionValue">How abstract should the recommendation be? - Higher Values result into more Knn-Neighbours and so more Category-Distance between Posts</param>
/// <returns>Returns a ptree Object of the ids (Simple JSON-Array) to add it into another ptree</returns>
ptree getFeed(const int accountId, const std::string accountName, const int amount, mongocxx::pool& pool, const int abstractionValue);

/// <summary>
/// Sort post_ids personalized
/// </summary>
/// <param name="accountId">MongoDB _id of account (to find it in the DB)</param>
/// <param name="accountName">Username of the account</param>
/// <param name="ptreeIds">ptree Array of Ids (From HTML Post Body)</param>
/// <param name="pool">MongoCxx-Driver Pool (Because of Thread-Safetyness)</param>
/// <returns>Returns a ptree Object of the ids (Simple JSON-Array) to add it into another ptree</returns>
ptree sortPersonalizedIds(const int accountId, const std::string accountName, const ptree& ptreeIds, mongocxx::pool& pool);

#endif 
