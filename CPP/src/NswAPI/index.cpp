#include "NswAPI/index.h"

#include <boost/date_time.hpp>
#include <bsoncxx/json.hpp>
#include <bsoncxx/builder/basic/document.hpp>
#include <bsoncxx/builder/basic/kvp.hpp>
#include <chrono>
#include "main.h"
#include <mongocxx/client.hpp>
#include <mongocxx/pool.hpp>
#include "NswAPI/listener.h"
#include <thread>
#include "User/account.h"

using bsoncxx::builder::basic::kvp;
using bsoncxx::builder::basic::make_document;
using bsoncxx::builder::basic::make_array;

namespace NswAPI {

	std::shared_ptr<hnswlib::AlgorithmInterface<float>> productionIndex = nullptr;

	void makeFeed(
		const int account_id,
		const int abstraction_value,
		const int amount,
		std::unordered_set<int>& post_results
	) {
		// Get account-activities
		std::vector<int> post_ids, vote_ids;
		User::Account::getActivities(account_id, post_ids, vote_ids);
		if (post_ids.size() == 0 && vote_ids.size() == 0)
			return; // Nothing available

		std::set<int> account_activities(post_ids.begin(), post_ids.end());
		account_activities.insert(vote_ids.begin(), vote_ids.end());
		const int max_account_activities = account_activities.size();

		auto client = GLOBAL::MongoDB::mongoPool.acquire();
		auto post_data = (*client)["hive-discover"]["post_data"];

		// Run until result is full
		size_t loop_counter = 0;
		while (post_results.size() < amount && loop_counter < 100) {
			// Get a (random) batch of ids
			const size_t batchCount = std::min(max_account_activities, 25);
			bsoncxx::builder::basic::array batchIDs;
			{
				// get random Indexes
				std::set<int> rndIndexes;
				for (size_t i = 0; i < batchCount; ++i)
					rndIndexes.insert(std::rand() % max_account_activities);

				// Select them
				auto it = account_activities.begin();
				for (size_t i = 0; i < max_account_activities; ++i)
				{
					if (rndIndexes.count(i))
						batchIDs.append(*it);
					++it;
				}

			}

			// Get categories of them
			std::vector<std::vector<float>> batchCategories;
			batchCategories.reserve(batchCount);
			{
				auto cursor = post_data.find(make_document(kvp("_id", make_document(kvp("$in", batchIDs)))));
				for (const auto& document : cursor) {
					const auto elemCategories = document["categories"];
					if (elemCategories.type() != bsoncxx::type::k_array)
						continue; // Not analyzed

					const bsoncxx::array::view category{ elemCategories.get_array().value };
					std::vector<float> data(46);

					// Parse data and push it					
					auto d_it = data.begin();
					for (auto c_it = category.begin(); c_it != category.end(), d_it != data.end(); ++d_it, ++c_it)
						*d_it = c_it->get_double().value;

					batchCategories.push_back(data);
				}
			}

			// Get similar Posts and reshape from 2d to 1d (flatten)
			std::set<int> results;
			{
				// Search
				const int k = abstraction_value + 5 + loop_counter;
				std::vector<std::vector<int>> all_results;
				getSimilarPostsByCategory(batchCategories, k, all_results);

				// Flatten the 2d results			
				for (const auto& r_item : all_results)
					results.insert(r_item.begin(), r_item.end());

			}

			// We do not have to check langs, because only english posts are categorized and in our Index
			// Check languages and if they are good, insert into post_results

			// Insert in post_results
			if (results.size() + post_results.size() <= amount) {
				// Insert all Items, it is (maybe not) enough
				post_results.insert(results.begin(), results.end());
			}
			else {
				// Insert Random Elements
				// Get random Indexes
				const int rndElementsCount = amount - post_results.size();
				std::set<int> rndIndexes = {};
				while (rndIndexes.size() < rndElementsCount)
					rndIndexes.insert(std::rand() % results.size());

				// Insert these randoms Elements
				size_t counter = 0;
				for (auto it = results.begin(); it != results.end(); ++it, ++counter) {
					if (rndIndexes.count(counter)) // Random Index reached ==> insert
						post_results.insert(*it);
				}
			}

			// Next round
			++loop_counter;
		}
	}

	void getSimilarPostsByCategory(const std::vector<std::vector<float>>& query, const int k, std::vector<std::vector<int>>& result)
	{
		if (productionIndex == nullptr)
			return;

		for (const auto& q_data : query) {
			// Search
			auto gd = productionIndex->searchKnn(q_data.data(), k);
			std::vector<int> posts;
			posts.reserve(gd.size());

			// Push them
			while (!gd.empty()) {
				const auto element = gd.top();
				posts.push_back(element.second);
				gd.pop();
			}

			result.push_back(posts);
		}
	}

	void buildIndex() {
		// Establish connection
		mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
		auto collection = (*client)["hive-discover"]["post_data"];

		// Prepare query
		bsoncxx::types::b_date minDate = bsoncxx::types::b_date(std::chrono::system_clock::now() - std::chrono::hours{ 10 * 24 });
		bsoncxx::v_noabi::document::view_or_value findQuery = make_document(
			kvp("timestamp", make_document(kvp("$gt", minDate)))
		);

		// init AlgorithmInterface with 25 starting elements
		size_t alg_ifcCapacity = 25;
		hnswlib::L2Space space(46);
		std::shared_ptr<hnswlib::AlgorithmInterface<float>> currentIndex = std::shared_ptr<hnswlib::AlgorithmInterface<float>>(
			new hnswlib::HierarchicalNSW<float>(&space, alg_ifcCapacity)
		);

		// Enter all docs
		auto cursor = collection.find(findQuery);
		size_t elementCounter = 0;
		for (const auto& doc : cursor) {
			const bsoncxx::document::element elemCategory = doc["categories"];
			const bsoncxx::document::element elemId = doc["_id"];

			// Check if post is valid and prepared
			if (elemCategory.type() != bsoncxx::type::k_array)
				continue;
			if (elemId.type() != bsoncxx::type::k_int32)
				continue;

			// Convert categories to std::vector<float>
			const bsoncxx::array::view category{ elemCategory.get_array().value };
			std::vector<float> data(46);
			auto d_it = data.begin();
			for (auto c_it = category.begin(); c_it != category.end(), d_it != data.end(); ++d_it, ++c_it)
				*d_it = c_it->get_double().value;

			// add to index
			hnswlib::labeltype _id = elemId.get_int32().value;
			currentIndex->addPoint(data.data(), _id);
			++elementCounter;

			if (elementCounter >= alg_ifcCapacity) {
				// Resize AlgorithmInterface
				alg_ifcCapacity += 25;
				static_cast<hnswlib::HierarchicalNSW<float>*>(currentIndex.get())->resizeIndex(alg_ifcCapacity);
			}
		}

		std::cout << "[INFO] Created PostIndex! Actual elements: " << elementCounter << std::endl;
		productionIndex = currentIndex;
	}

	void start() {
		// Start API
		Listener::startAPI();

		// While-Loop does everything every 10 Minutes
		while (1) {
			buildIndex();

			std::this_thread::sleep_for(std::chrono::minutes(15));
		}
	}

}