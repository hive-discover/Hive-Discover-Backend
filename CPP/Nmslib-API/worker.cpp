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

// Method to create the index
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
	auto targetIds = bsoncxx::builder::basic::array{};

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

			targetIds.append(elemId.get_int32().value);
			hnswlib::labeltype _id = elemId.get_int32().value;
			currentIndex->addPoint(data.data(), _id);
		}

		++counter;
		if (counter > 1000)
			break;
	}

	std::cout << "Created PostIndex! Max elements: " << maxElements << std::endl;
	return currentIndex;
}

// Endless Thread to periodically create an Index
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
		return std::vector<std::vector<int>>(0);

	int resultIndex = 0;
	std::vector<std::vector<int>> result(posts.size());
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

		result[resultIndex] = postResult;
		++resultIndex;
	}
	
	return result;
}

void addLang(const bsoncxx::document::element& docLang, std::map<std::string, float>& langs, const double factor = 1) {
	if (docLang.type() == type::k_array) {
		for (const bsoncxx::array::element& langItem : docLang.get_array().value) {
			const bsoncxx::document::element itemScore = langItem["x"];
			const bsoncxx::document::element itemLang = langItem["lang"];

			if (itemScore.type() == type::k_double && itemLang.type() == type::k_utf8) {
				// Check if already inside and just add / Else set it
				const std::string currentLang = itemLang.get_utf8().value.to_string();

				if (langs.count(currentLang))
					langs[currentLang] += itemScore.get_double().value * factor;
				else
					langs[currentLang] = itemScore.get_double().value * factor;
			}
		}
	}
}

ptree getFeed(const int accountId, const std::string accountName, const int amount, mongocxx::pool& pool, const int abstractionValue = 0) {
	bsoncxx::builder::basic::array accLangs{};
	std::set<int> accVotes, accPosts, accActivities, feedItems;
	bool getterFinished = false;

	std::thread activitiesGetter([accountId, accountName, &accLangs, &accVotes, &accPosts, &accActivities, &pool, &getterFinished] {
		std::map<std::string, float> langs;

		// Gather Post IDs and Langs
		std::thread postGetter([accountName, &accPosts, &accActivities, &langs, &pool] {
			auto client = pool.acquire();
			auto coll = (*client)["hive-discover"]["post_info"];

			// Find Ids
			bsoncxx::builder::basic::array postIDs;
			for (const bsoncxx::document::view& doc : coll.find(make_document(kvp("author", accountName)))) {
				const bsoncxx::document::element elemId = doc["_id"];

				if (elemId.type() == type::k_int32) {
					const int _id = elemId.get_int32().value;
					postIDs.append(_id);
					accPosts.insert(_id);
					accActivities.insert(_id);
				}				
			}

			// Gather Langs from post_data  accPosts
			coll = (*client)["hive-discover"]["post_data"];
			for (const bsoncxx::document::view& doc : coll.find(make_document(kvp("_id", make_document(kvp("$in", postIDs))))))
				addLang(doc["lang"], langs, 2);
		});

		// Gather Votes IDs and Langs
		std::thread votesGetter([accountId, &accVotes, &accActivities, &langs, &pool] {
			auto client = pool.acquire();
			auto coll = (*client)["hive-discover"]["post_data"];

			for (const bsoncxx::document::view& doc : coll.find(make_document(kvp("votes", accountId)))) {
				// Append _id and langs
				const bsoncxx::document::element elemId = doc["_id"];	
				addLang(doc["lang"], langs, 1);

				if (elemId.type() == type::k_int32) {
					accVotes.insert(elemId.get_int32().value);
					accActivities.insert(elemId.get_int32().value);
				}				
			}
		});

		// Wait for both
		votesGetter.join();
		postGetter.join();

		// Lang Post-Processing:
		// Calc Total, then Percentages and when they got more than 15% --> add to bson::array
		float totalScore = 0; 
		for (const auto& langItem : langs)
			totalScore += langItem.second;
		for (const auto& langItem : langs) {
			if((langItem.second / totalScore) > 0.15)
				accLangs.append(langItem.first);
		}

		getterFinished = true;
	});

	auto client = pool.acquire();
	auto coll = (*client)["hive-discover"]["post_data"];

	// Find similar Posts while:
	// 1. Getter Thread has not finished
	//	OR
	// 2. feedItems is not full AND some Votes/Posts are available	(else it will never find anything similar)
	//  OR
	// 3. loopIndex >= 1000 (nothing can be found)
	unsigned int loopIndex = 0;
	bsoncxx::v_noabi::document::view_or_value findQuery;
	bsoncxx::builder::basic::array choosedIds;
	std::vector<std::vector<float>> choosedPosts;
	std::vector<std::vector<int>> similarIds;
	while (1) {
		while (!getterFinished && accVotes.size() == 0 && accPosts.size() == 0)
			std::this_thread::sleep_for(std::chrono::nanoseconds(250));

		if (feedItems.size() >= amount || (accVotes.size() == 0 && accPosts.size() == 0))
			break; // enough Posts or GetterThread has finished; but no Posts/Votes are available

		// Get some randoms
		choosedIds = {};
		std::set<unsigned long long> randomIndexes = { accActivities.size() % rand(), accActivities.size() % rand(), accActivities.size() % rand(), accActivities.size() % rand(), accActivities.size() % rand(), accActivities.size() % rand() };
		size_t currentIndex = 0;
		for (const auto& elem : accActivities) {
			if (randomIndexes.count(currentIndex))
				choosedIds.append(elem);
			++currentIndex;
		}
			

		findQuery = make_document(kvp("_id", make_document(kvp("$in", choosedIds))));

		// Get categories from randoms
		choosedPosts = {};
		for (const auto& doc : coll.find(findQuery)) {
			const bsoncxx::document::element elemCategory = doc["categories"];

			if (elemCategory.type() == type::k_array) {
				const bsoncxx::array::view category{ elemCategory.get_array().value };
				std::vector<float> data(46);
				int dataIndex = 46;

				for (; dataIndex; --dataIndex)
					data[dataIndex - 1] = category[dataIndex - 1].get_double().value;
				choosedPosts.push_back(data);
			}
		}

		// Find similars and remove known ones (his Votes/Posts)
		// K gets increased by every Iteration to find surely something
		similarIds = findSimilarPostsByCategory(choosedPosts, (7 + loopIndex + abstractionValue));
		for (const auto& IdsPerPost : similarIds) {
			// Iterate over every similar Id per Post
			for (const int& sId : IdsPerPost) {
				if (!feedItems.count(sId) && !accPosts.count(sId) && !accVotes.count(sId))
					feedItems.insert(sId); 
			}		
		}

		// TODO: Check langs

		++loopIndex;
	}


	// Got everything --> make ptree response
	ptree rootTree, resultTree;
	rootTree.put("status", "ok");
	for (const int& simID : feedItems)
	{
		ptree elem;
		elem.put("", simID);
		resultTree.push_back(std::make_pair("", elem));
	}
	rootTree.add_child("result", resultTree);

	activitiesGetter.detach();
	return rootTree;
}

