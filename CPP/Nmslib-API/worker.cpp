#include <iostream>
#include <iterator>
#include <math.h> 
#include <algorithm>
#include <chrono>
#include <thread>
#include <string>
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
		if (counter > 10)
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



ptree getFeed(const int accountId, const std::string accountName, const size_t amount, mongocxx::pool& pool) {
	ptree rootTree, resultTree;
	bsoncxx::builder::basic::array accLangs{};// , votes{}, ownPosts{};
	std::unordered_set<int> feedItems(amount), accVotes{}, accPosts{};

	std::thread activitiesGetter([accountId, accountName, &accLangs, &accVotes, &accPosts, &pool] {
		std::unordered_set<std::pair<std::string, double>> langs{};

		// Gather Post IDs and Langs
		std::thread postGetter([accountName, &accPosts, &langs, &pool] {
			auto client = pool.acquire();
			auto coll = (*client)["hive-discover"]["post_info"];

			// Find Ids
			for (const bsoncxx::document::view& doc : coll.find(make_document(kvp("author", accountName)))) {
				const bsoncxx::document::element elemId = doc["_id"];

				if (elemId.type() == type::k_int32)
					accPosts.insert(elemId.get_int32().value);
			}

			//TODO: find langs
		});

		// Gather Post IDs and Langs
		std::thread votesGetter([accountId, &accVotes, &langs, &pool] {
			auto client = pool.acquire();
			auto coll = (*client)["hive-discover"]["post_data"];

			for (const bsoncxx::document::view& doc : coll.find(make_document(kvp("votes", accountId)))) {
				const bsoncxx::document::element elemId = doc["_id"];
				const bsoncxx::document::element elemLang = doc["lang"];
				

				if (elemId.type() == type::k_int32)
					accVotes.insert(elemId.get_int32().value);

				if (elemLang.type() == type::k_array) {
					const bsoncxx::array::view postLangs{ elemLang.get_array().value };

					for (const bsoncxx::array::element& langItem : postLangs) {
						const bsoncxx::document::element itemScore = langItem["x"];
						const bsoncxx::document::element itemLang = langItem["lang"];

						//if (itemScore.type() == type::k_double && itemLang.type() == type::k_utf8)
							//langs.insert(std::make_pair<std::string, double>(itemLang.get_utf8().value, itemScore.get_double().value));
					} 
				} 					
			}
			});

		votesGetter.join();
		postGetter.join();
	});

	rootTree.put("status", "ok");
	// Test with randoms
	auto client = pool.acquire();
	auto coll = (*client)["hive-discover"]["post_data"];

	std::vector<std::vector<float>> posts;
	mongocxx::cursor cursor = coll.find({});
	for (const bsoncxx::document::view& doc : cursor) {
		const bsoncxx::document::element elemCategory = doc["categories"];
		const bsoncxx::document::element elemId = doc["_id"];

		std::vector<float> p;
		for (const auto& x : elemCategory.get_array().value)
			p.push_back(x.get_double().value);
		posts.push_back(p);

		if(posts.size() > 5)
			break;
	}

	for (const std::vector<int>& simForPost : findSimilarPostsByCategory(posts)) {
		for (const int& simID : simForPost) {
			feedItems.insert(simID);
		}			
	}

	for (const int& simID : feedItems)
	{
		ptree elem;
		elem.put("", simID);
		resultTree.push_back(std::make_pair("", elem));
	}
	rootTree.add_child("result", resultTree);

	activitiesGetter.join();
	return rootTree;
}

