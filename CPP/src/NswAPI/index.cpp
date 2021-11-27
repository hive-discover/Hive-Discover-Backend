#include "NswAPI/index.h"

#include <boost/date_time.hpp>
#include <boost/thread/thread_pool.hpp>
#include <bsoncxx/builder/basic/document.hpp>
#include <bsoncxx/builder/basic/kvp.hpp>
#include <bsoncxx/json.hpp>
#include <chrono>
#include <fstream>
#include "main.h"
#include <mongocxx/bulk_write.hpp>
#include <mongocxx/client.hpp>
#include <mongocxx/pool.hpp>
#include <mongocxx/model/update_one.hpp>
#include "NswAPI/listener.h"
#include <thread>
#include <stack>
#include "User/account.h"

using bsoncxx::builder::basic::kvp;
using bsoncxx::builder::basic::make_document;
using bsoncxx::builder::basic::make_array;

namespace NswAPI {

	hnswlib::L2Space space(46);

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
				Categories::getSimilarPostsByCategory(batchCategories, k, all_results);

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

	void start() {
		// Start API
		Listener::startAPI();

		// Threads for Index Builds and sub-methods
		//	* Post Category Index
		std::thread([]() {
			// Build Index and wait 15 Minutes to rebuild it

			while (1) {
				Categories::buildIndex();
				std::this_thread::sleep_for(std::chrono::minutes(15));
			}
		}).detach();

		//	* Account Interests Index
		std::thread([]() {
			// Build Index, then wait 20 Minutes and finally rebuild ALL profiles (long and intense calculation), that 
			// is why we first wait and then do it because on startup we need performance for other ressources...

			while (1) {
				Accounts::buildIndex();
				std::this_thread::sleep_for(std::chrono::minutes(20));
				Accounts::set_all_account_profiles();
			}		
		}).detach();
	}


	namespace Categories {
		std::shared_ptr<hnswlib::AlgorithmInterface<float>> productionIndex = nullptr;

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
			//hnswlib::L2Space space(46);
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

	}

	namespace Accounts {
		std::shared_ptr<hnswlib::AlgorithmInterface<float>> productionIndex = nullptr;

		std::vector<float> calc_account_profile(const int account_id) {
			// Get account activites
			bsoncxx::builder::basic::array activity_ids;
			{
				std::vector<int> vector_post_ids, vector_vote_ids;
				User::Account::getActivities(account_id, vector_post_ids, vector_vote_ids);

				// Insert activites to bson::array
				for (const auto list : { vector_post_ids, vector_vote_ids }) {
					for (const auto& _id : list)
						activity_ids.append(_id);
				}
			}
			
			if (activity_ids.view().length() == 0)
				return {}; // Nothing to look at

			// Establish connection
			mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
			auto post_data = (*client)["hive-discover"]["post_data"];
			auto cursor = post_data.find(
				make_document(
					kvp("_id", make_document(kvp("$in", activity_ids)))
				)
			);

			// Enter all of them
			std::vector<float> account_data(46);
			size_t post_count = 0;
			for (const auto& post_doc : cursor) {
				const auto elemCats = post_doc["categories"];
				if (elemCats.type() != bsoncxx::type::k_array)
					continue; // Not usable

				// Add to account_data
				post_count += 1;
				const bsoncxx::array::view category{ elemCats.get_array().value };
				auto it = category.begin();
				for (size_t i = 0; i < account_data.size(); ++i, ++it)
					account_data[i] += it->get_double().value;
			}

			if (post_count == 0)
				return {}; // Nothing is there

			// Calc average and return it
			for (auto& x : account_data)
				x = x / post_count;

			return account_data;
		}

		void set_all_account_profiles() {
			// Get a connection
			mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
			auto collection = (*client)["hive-discover"]["account_info"];

			// Get all accounts and prepare bulk update storage and lock
			mongocxx::options::find opts;
			opts.projection(make_document(kvp("_id", 1)));
			auto cursor = collection.find({}, opts);
			std::stack<mongocxx::v_noabi::model::update_one> update_bulk;
			std::mutex bulk_lock;

			// Start task on all accounts
			std::atomic<int> workers_count(0);
			boost::asio::thread_pool th_pool(3);
			for (const auto& account_doc : cursor) {
				++workers_count;
				const int account_id = account_doc["_id"].get_int32().value;

				// Producer-threads
				boost::asio::post(th_pool,
					[account_id, &update_bulk, &bulk_lock, &workers_count]() {
						// Get acc profile
						const std::vector<float> profile = calc_account_profile(account_id);

						if (profile.size()) {
							// Convert std::vector to bson::array
							bsoncxx::builder::basic::array barr_profile;
							for (const auto& x : profile)
								barr_profile.append(x);

							// Create bulk-model
							auto update_model = mongocxx::model::update_one(
								make_document(kvp("_id", account_id)), // Filter
								make_document(kvp("$set", make_document(kvp("interests", barr_profile)))) // Update
							);

							// Lock vector and push bulk-model
							std::lock_guard<std::mutex> lock(bulk_lock);
							update_bulk.push(update_model);
						}

						// Mark that we finished
						--workers_count;
					});
			}

			// Consumer-Task
			while (workers_count > 0 || update_bulk.size() > 0) {
				if (update_bulk.size() < 25 && workers_count > 0) {
					// We can wait, some elements will also come
					std::this_thread::sleep_for(std::chrono::milliseconds(250));
					continue;
				}

				// we got enough to do ==> extract bulk-models
				mongocxx::options::bulk_write bulkWriteOption;
				bulkWriteOption.ordered(false);			
				mongocxx::bulk_write bulk = collection.create_bulk_write(bulkWriteOption);

				{
					std::lock_guard<std::mutex> lock(bulk_lock); // locking
					while (update_bulk.size()) {
						// Insert elements into bulk-obj
						bulk.append(update_bulk.top());
						update_bulk.pop();
					}						
				}
				
				try {
					// Perform bulk-update
					bulk.execute();
				}
				catch (std::exception ex) {
					std::cout << "[ERROR] Exception raised at set_all_account_profiles(): " << ex.what() << std::endl;
				}
				
			}

			th_pool.join(); // Useless, but to be sure that everything has finished
		}

		void buildIndex() {
			// Establish connection and prepare query
			mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
			auto collection = (*client)["hive-discover"]["account_info"];
			bsoncxx::v_noabi::document::view_or_value findQuery = make_document(
				kvp("interests", make_document(kvp("$exists", true)))
			);

			// init AlgorithmInterface with 25 starting elements
			size_t alg_ifc_capacity = 25;
			//hnswlib::L2Space space(46);
			std::shared_ptr<hnswlib::AlgorithmInterface<float>> current_index = std::shared_ptr<hnswlib::AlgorithmInterface<float>>(
				new hnswlib::HierarchicalNSW<float>(&space, alg_ifc_capacity)
				);

			// Enter all docs
			auto cursor = collection.find(findQuery);
			size_t elementCounter = 0;
			for (const auto& account_doc : cursor) {			
				const int account_id = account_doc["_id"].get_int32().value;
				const bsoncxx::document::element elemInterests = account_doc["interests"];
				if (elemInterests.type() != bsoncxx::type::k_array)
					continue;

				// Convert bson::array to std::vector<float>
				const bsoncxx::array::view interests{ elemInterests.get_array().value };
				std::vector<float> data(46);
				auto d_it = data.begin();
				for (auto c_it = interests.begin(); c_it != interests.end(), d_it != data.end(); ++d_it, ++c_it)
					*d_it = c_it->get_double().value;

				// Add Data Entry to Index and Increment counter
				hnswlib::labeltype _id = account_id;
				current_index->addPoint(data.data(), _id);
				++elementCounter;

				// Check, if we need to resize
				if (elementCounter >= alg_ifc_capacity) {
					// Resize
					alg_ifc_capacity += 25;
					static_cast<hnswlib::HierarchicalNSW<float>*>(current_index.get())->resizeIndex(alg_ifc_capacity);
				}
			}

			productionIndex = current_index;
			std::cout << "[INFO] Created Account-Index with " << alg_ifc_capacity << " elements! " << std::endl;
		}

		void getSimilarAccounts(
			const std::vector<std::vector<float>>& query,
			const int k,
			std::vector<std::vector<int>>& result
		) {
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
	}
	
}