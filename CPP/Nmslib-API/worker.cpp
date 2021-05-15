#include <iostream>
#include <iterator>
#include <math.h> 
#include <algorithm>
#include <chrono>
#include <thread>
#include <random>
#include <string>
#include <map>
#include <set>
#include <unordered_set>

#include <vector>
#include <assert.h>
#include "hnswlib/hnswlib/hnswlib.h"

#include <mongocxx/client.hpp>
#include <mongocxx/pool.hpp>
#include <bsoncxx/json.hpp>
#include <bsoncxx/builder/basic/document.hpp>
#include <bsoncxx/builder/basic/kvp.hpp>

#include <boost/date_time.hpp>
#include <boost/date_time/gregorian/gregorian.hpp>
#include <boost/property_tree/ptree.hpp>
#include "main.hpp"

using bsoncxx::type;
using namespace boost::property_tree;
using bsoncxx::builder::basic::kvp;
using bsoncxx::builder::basic::make_document;
using bsoncxx::builder::basic::make_array;

hnswlib::AlgorithmInterface<float>* postIndex = NULL;


/// <summary>
/// Method to create the Post-Index with all Posts within the last 10 days
/// </summary>
/// <param name="client">MongoCxx-Driver Client. This object is not thread-safe! Do not run this Method in anotehr thread than the client is created!</param>
/// <returns>Calculated Knn-Index</returns>
hnswlib::AlgorithmInterface<float>* createPostIndex(mongocxx::v_noabi::pool::entry client) {
	// Get Client from Pool
	auto coll = (*client)["hive-discover"]["post_data"];

	// Prepare findQuery and Datetime from 10 days ago
	std::chrono::time_point<std::chrono::system_clock> now = std::chrono::system_clock::now();
	bsoncxx::types::b_date minDate = bsoncxx::types::b_date(now - std::chrono::hours{ 10 * 24 });
	bsoncxx::v_noabi::document::view_or_value findQuery = make_document(kvp("timestamp", make_document(kvp("$gt", minDate))));

	//Count documents and define currentIndex with a Maximum of Count + 7,5% (buffer)
	int64_t maxElements = ceil(coll.count_documents(findQuery) * 1.075);
	hnswlib::L2Space space(46);
	hnswlib::AlgorithmInterface<float>* currentIndex = new hnswlib::HierarchicalNSW<float>(&space, maxElements);

	
	int counter = 0;

	auto cursor = coll.find(findQuery);
	for (const bsoncxx::document::view& doc : cursor) {
		const bsoncxx::document::element elemCategory = doc["categories"];
		const bsoncxx::document::element elemId = doc["_id"];

		if (elemCategory.type() == type::k_array && elemId.type() == type::k_int32) {
			const bsoncxx::array::view category{ elemCategory.get_array().value };
			std::vector<float> data(1 * 46);
			int dataIndex = 0;

			for (const bsoncxx::array::element& value : category) {
				if (value.type() == type::k_double) {
					data[dataIndex] = value.get_double().value;
					++dataIndex;
				}
			}

			//targetIds.append(elemId.get_int32().value);
			hnswlib::labeltype _id = elemId.get_int32().value;
			currentIndex->addPoint(data.data(), _id);

			++counter;
			if (counter > 250)
				break;
		}
	}

	std::cout << "Created PostIndex! Max elements: " << maxElements << std::endl;
	return currentIndex;
}

/// <summary>
/// Endless Thread to periodically create a Post-Index
/// </summary>
/// <param name="parameter">std::pair of the MongoCxx-Pool (Thread-Safety) and a bool</param>
void manageIndex(std::pair<mongocxx::pool&, bool> parameter) {
	mongocxx::pool& pool = parameter.first;
	bool exitCmd = parameter.second;

	while (!exitCmd) {
		hnswlib::AlgorithmInterface<float>* currentIndex = createPostIndex(pool.acquire());
		delete postIndex;
		postIndex = currentIndex;
		currentIndex = NULL;

		std::this_thread::sleep_for(std::chrono::minutes(25));
	}
}

/// <summary>
/// Get similar Posts like the ones given
/// </summary>
/// <param name="posts">List categories from the posts</param>
/// <param name="k">Count of Neighbours</param>
/// <returns>List of similar Ids per Posts</returns>
std::vector<std::vector<int>> findSimilarPostsByCategory(std::vector<std::vector<float>> posts, const size_t k = 25) {
	if (postIndex == NULL)
		return std::vector<std::vector<int>>{};

	std::vector<std::vector<int>> result{};
	result.reserve(posts.size());
	for (const std::vector<float>& data : posts) {
		// Find similar per Post and set it at the correct index
		auto gd = postIndex->searchKnn(data.data(), k);
		int gdIndex = gd.size() - 1;
		std::vector<int> postResult(gd.size());

		// Reverse and remove Distance at the same time
		while (!gd.empty()) {
			const std::pair<float, hnswlib::labeltype> result = gd.top();
			const float rDis = std::get<0>(result);
			const hnswlib::labeltype rID = std::get<1>(result);
			postResult[gdIndex] = rID;

			gd.pop();
			--gdIndex;
		}

		result.push_back(postResult);
	}
	
	return result;
}

/// <summary>
/// Get an overview of the used langs inside the Posts. Add all lang-scores together and caluclate Percentages.
/// Every lang over 15% is added to accLangs
/// </summary>
/// <param name="postIds">Which ids should be processed?</param>
/// <param name="accLangs">Where should the Langs be inserted?</param>
/// <param name="pool">MongoCxx-Driver Pool (Because of Thread-Safetyness)</param>
/// <returns>std::Thread Object</returns>
std::thread getLangsFromIds(const std::vector<int>& postIds, bsoncxx::builder::basic::array& accLangs, mongocxx::pool& pool) {
	return std::thread([&postIds, &accLangs, &pool]{
		// Convert vector* to bson::array
		bsoncxx::builder::basic::array barrPostIds {};
		for (size_t i = postIds.size(); i; --i)
			barrPostIds.append(postIds[i - 1]);
		
		auto client = pool.acquire();
		auto coll = (*client)["hive-discover"]["post_data"];

		// Retrieve all Langs
		std::map<std::string, float> langs{};
		bsoncxx::document::element elemLangs, itemScore, itemLang;
		std::string currentLang;
		for (const bsoncxx::document::view& doc : coll.find(make_document(kvp("_id", make_document(kvp("$in", barrPostIds)))))) {
			elemLangs = doc["lang"];

			// is array? - Yes, then iterate and process everyone
			if (elemLangs.type() == type::k_array) {
				for (const bsoncxx::array::element& langItem : elemLangs.get_array().value) {
					itemScore = langItem["x"];
					itemLang = langItem["lang"];

					// are score and lang types correct? - Yes, then add it into map
					if (itemScore.type() == type::k_double && itemLang.type() == type::k_utf8) {
						currentLang = itemLang.get_utf8().value.to_string();

						if (langs.count(currentLang))
							langs[currentLang] += itemScore.get_double().value;
						else
							langs[currentLang] = itemScore.get_double().value;
					}
				}
			}
		}

		// Calculate Percentages and then check if Lang is over 15%
		float totalScore = 0; 
		for (const auto& langItem : langs)
			totalScore += langItem.second;

		for (const auto& langItem : langs) { 
			if ((langItem.second / totalScore) > 0.15)
				accLangs.append(langItem.first);
		}

	});
}

/// <summary>
/// Find all Activities by an Account: Ids of liked and self-written Posts
/// </summary>
/// <param name="accountId">MongoDB _id of account (to find it in the DB)</param>
/// <param name="accountName">Username of the account</param>
/// <param name="accActivities">Pointer to the Vector where the Ids should be inserted</param>
/// <param name="pool">MongoCxx-Driver Pool (Because of Thread-Safetyness)</param>
void getActivitiesFromAccount(const int accountId, const std::string& accountName, std::vector<int>* accActivities, mongocxx::pool& pool) {
	// Post Getter
	std::thread postGetter([&pool, &accountName, &accActivities] {
		auto client = pool.acquire();
		auto coll = (*client)["hive-discover"]["post_info"];
		bsoncxx::v_noabi::document::view_or_value findQuery{ make_document(kvp("author", accountName)) };
		
		// First count documents to reserve memory and double the value because posts count double!
		// + size() + 5 because the other thread could already have set it and also to have a buffer
		accActivities->reserve(coll.count_documents(findQuery) * 2 + accActivities->size() + 5);

		// Retrieve all Ids
		bsoncxx::document::element elemId;
		for (const bsoncxx::document::view& doc : coll.find(findQuery)) {
			elemId = doc["_id"];

			if (elemId.type() == type::k_int32) {
				accActivities->push_back(elemId.get_int32().value);
				accActivities->push_back(elemId.get_int32().value);
			}			
		}
	});
	
	// Vote Getter
	std::thread voteGetter([&pool, &accountId, &accActivities] {
		auto client = pool.acquire();
		auto coll = (*client)["hive-discover"]["post_data"];
		bsoncxx::v_noabi::document::view_or_value findQuery{ make_document(kvp("votes", accountId)) };

		// First count documents to reserve memory
		// + size() + 5 because the other thread could already have set it and also to have a buffer
		accActivities->reserve(coll.count_documents(findQuery) + accActivities->size() + 5);

		// Retrieve all Ids
		bsoncxx::document::element elemId;
		for (const bsoncxx::document::view& doc : coll.find(findQuery)) {
			elemId = doc["_id"];

			if (elemId.type() == type::k_int32)
				accActivities->push_back(elemId.get_int32().value);
		}
	});

	// Wait for both
	postGetter.join();
	voteGetter.join();
}



//	*******
//		PUBLIC AREA
//	*******



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
ptree getFeed(const int accountId, const std::string accountName, const int amount, mongocxx::pool& pool, const int abstractionValue = 0) {
	// Get Account Activities (Posts and Votes) and start the Lang-Calculator
	std::vector<int> accActivities{};
	getActivitiesFromAccount(accountId, accountName, &accActivities, pool);
	bsoncxx::builder::basic::array accLangs{};
	std::thread langGetter = getLangsFromIds(accActivities, accLangs, pool);

	auto client = pool.acquire();
	auto coll = (*client)["hive-discover"]["post_data"];

	// Create Feed while:
	//   1. feedItems isn't full
	//   2. accActivities's size() isn't equal to 0 (higher than 0 is interpreted as true)
	//	 3. loopIndex isn't over 1000
	size_t loopIndex = 0;
	std::vector<std::vector<float>> choosedPosts{};
	std::vector<std::vector<int>> similarIds{};
	std::set<int> feedItems{};
	bsoncxx::v_noabi::document::view_or_value findQuery;
	bsoncxx::builder::basic::array choosedIds{};
	while (feedItems.size() < amount && accActivities.size() && loopIndex <= 1000) {
		// Get randoms (max. 50)
		choosedIds.clear();
		for (size_t i = std::min(rand() % accActivities.size(), 50ULL); i; --i)
			choosedIds.append(*(accActivities.begin() + (rand() % (accActivities.size() - 1))));

		// Retrieve categories
		choosedPosts.clear();
		choosedPosts.reserve(choosedIds.view().length());
		bsoncxx::document::element elemCategory;
		bsoncxx::array::view category;
		for (const bsoncxx::document::view& doc : coll.find(make_document(kvp("_id", make_document(kvp("$in", choosedIds)))))) {
			elemCategory = doc["categories"];

			if (elemCategory.type() == type::k_array) {
				category = elemCategory.get_array().value;
				std::vector<float> data(46);		

				for (size_t dataIndex = 46; dataIndex; --dataIndex)
					data[dataIndex - 1] = category[dataIndex - 1].get_double().value;
				choosedPosts.push_back(data);
			}
		} 
		
		// Find similar and reshape to 1d
		choosedIds.clear();
		similarIds = findSimilarPostsByCategory(choosedPosts, (5 + loopIndex + abstractionValue));
		for (const auto& IdsPerPost : similarIds) {
			// Iterate over every similar Id per Post
			for (const int& sId : IdsPerPost) {
				if (!feedItems.count(sId))
					choosedIds.append(sId);
			}
		}		

		// Check langs (if some Items inside choosedIds)
		if (choosedIds.view().length()) {
			if (langGetter.joinable())
				langGetter.join();

			findQuery = make_document(
				kvp("_id", make_document(
					kvp("$in", choosedIds))
				),
				kvp("lang", make_document(
					kvp("$elemMatch", make_document(
						kvp("lang", make_document(
							kvp("$in", accLangs)
						))
					))
				))
			);

			bsoncxx::document::element elemID;
			for (const auto& doc : coll.find(findQuery)) {
				elemID = doc["_id"];

				if (elemID.type() == type::k_int32)
					feedItems.insert(elemID.get_int32().value);
			}
		}
		++loopIndex;
	}
	
	ptree resultTree{};
	if (feedItems.size() > 0) {
		// Select randoms and insert them into resultTree
		std::set<size_t> usedIterators{};
		std::set<int>::iterator it;

		size_t k;
		for (size_t i = amount; i; --i){	
			while (1) {
				k = (rand() % feedItems.size());

				if (!usedIterators.count(k)) {
					// Got random, unsued k
					usedIterators.insert(k); 

					// Skip to Pos			
					for (it = feedItems.begin(); k; --k)
						++it; 

				
					// Enter random
					ptree elem;				
					elem.put("", *it);
					resultTree.push_back(std::make_pair("", elem));
					break;
				}
			}

			
		}
		
	}

	
	return resultTree;
}

/// <summary>
/// Sort post_ids personalized
/// </summary>
/// <param name="accountId">MongoDB _id of account (to find it in the DB)</param>
/// <param name="accountName">Username of the account</param>
/// <param name="ptreeIds">ptree Array of Ids (From HTML Post Body)</param>
/// <param name="pool">MongoCxx-Driver Pool (Because of Thread-Safetyness)</param>
/// <returns>Returns a ptree Object of the ids (Simple JSON-Array) to add it into another ptree</returns>
ptree sortPersonalizedIds(const int accountId, const std::string accountName, const ptree& ptreeIds, mongocxx::pool& pool) {
	hnswlib::AlgorithmInterface<float>* accIndex;
	hnswlib::L2Space space(46);
	std::thread accIndexGetter([&accIndex, &space, &accountName, &accountId, &pool]() {
		std::vector<int> accActivites{};
		getActivitiesFromAccount(accountId, accountName, &accActivites, pool);

		// Convert vector to bson::array
		bsoncxx::builder::basic::array barrAccActivites{};
		for (auto it = accActivites.begin(); it != accActivites.end(); ++it)
			barrAccActivites.append(*it);

		// Prepare Database Connection and Find-Query
		auto client = pool.acquire();
		auto coll = (*client)["hive-discover"]["post_data"];
		bsoncxx::v_noabi::document::view_or_value findQuery = make_document(kvp("_id", make_document(kvp("$in", barrAccActivites))));

		// Create accountIndex
		int64_t maxElements = ceil(coll.count_documents(findQuery) * 1.075);
		accIndex = new hnswlib::HierarchicalNSW<float>(&space, maxElements);

		std::vector<float> data(46);
		bsoncxx::document::element elemCategory, elemId;
		bsoncxx::array::view category;
		for (const auto& doc : coll.find(findQuery)) {
			elemCategory = doc["categories"];
			elemId = doc["_id"];

			if (elemCategory.type() == type::k_array && elemId.type() == type::k_int32) {
				// Convert double-bson-array to float-vector
				size_t dataIndex = 0;
				for (const bsoncxx::array::element& value : elemCategory.get_array().value) {
					if (value.type() == type::k_double) {
						data[dataIndex] = value.get_double().value;
						++dataIndex;
					}
				}

				hnswlib::labeltype _id = elemId.get_int32().value;
				accIndex->addPoint(data.data(), _id);
			}
		}
	});
	
	// Convert ptree-array into bson::array
	bsoncxx::builder::basic::array barrAccActivites{};
	for (auto pair : ptreeIds)
		barrAccActivites.append(pair.second.get_value<int>());

	auto client = pool.acquire();
	auto coll = (*client)["hive-discover"]["post_data"];

	// Get categories of Ids
	std::vector<float> data(46);
	bsoncxx::document::element elemCategory, elemId;
	bsoncxx::array::view category;
	std::set<std::pair<int, std::vector<float>>> IdCategories{};
	bsoncxx::v_noabi::document::view_or_value findQuery = make_document(kvp("_id", make_document(kvp("$in", barrAccActivites))));
	for (const auto& doc : coll.find(findQuery)) {
		elemCategory = doc["categories"];
		elemId = doc["_id"];

		if (elemCategory.type() == type::k_array && elemId.type() == type::k_int32) {
			// Convert double-bson-array to float-vector
			size_t dataIndex = 0;
			for (const bsoncxx::array::element& value : elemCategory.get_array().value) {
				if (value.type() == type::k_double) {
					data[dataIndex] = value.get_double().value;
					++dataIndex;
				}
			}
			IdCategories.insert(std::pair<int, std::vector<float>>(elemId.get_int32().value, { data }));
		}
	}
	
	if (accIndexGetter.joinable()) // Wait to have the accIndex
		accIndexGetter.join();

	// Calc finally Distances
	std::vector<std::pair<int, float>> IdDistances{};
	IdDistances.reserve(IdCategories.size());

	for (auto& pair : IdCategories) {
		// Calc knn-distances and sum them up
		auto gd = accIndex->searchKnn(pair.second.data(), 5);

		float totalDistance = 0;
		while (!gd.empty()) {
			totalDistance += std::get<0>(gd.top());
			gd.pop();
		}

		IdDistances.push_back(std::pair<int, float>(pair.first, totalDistance));
	}	

	// Sort distances by increasing order (first is the best)
	sort(IdDistances.begin(), IdDistances.end(), 
		[] (const std::pair<int, float>&a, const std::pair<int, float>&b) {
		return (a.second < b.second);
	});

	// Append sorted Ids into ptree Result (first is the best)
	ptree resultTree{};
	for (const auto& pair : IdDistances) {
		ptree elem;
		elem.put("", pair.first);
		resultTree.push_back(std::make_pair("", elem));
	}

	delete accIndex;
	return resultTree;
}
