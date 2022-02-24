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

	template<typename T>
	void parseBinaryToVector(
		const uint8_t* first, 
		const uint32_t b_size, 
		std::vector<T>& result
	) {
		// Set size and enter all elements
		result.resize(b_size / sizeof(T));

		for (size_t i = 0; i < b_size / sizeof(T); ++i) 
			result[i] = *(reinterpret_cast<const T*>(first + i * sizeof(T)));		
	}

	template<typename T>
	void parseBinaryToVector(
		const bsoncxx::document::element& binary_element,
		std::vector<T>& result
	) {
		const bsoncxx::types::b_binary bin_data = binary_element.get_binary();
		parseBinaryToVector<T>(bin_data.bytes, bin_data.size, result);
	}

	template<typename T>
	uint8_t* parseVectorToBinary(
		const std::vector<T>& vector,
		uint32_t& b_size	
	) {
		// Set size and enter all binary elements to an bytes-array
		b_size = sizeof(T) * vector.size();
		uint8_t* first = new uint8_t[b_size];

		for (int i = 0; i < vector.size(); ++i) {
			// Convert item to binary
			uint8_t ures[sizeof(T)];
			memcpy(&ures, &vector[i], sizeof(T));

			// Push all bytes to first-array
			for (int k = 0; k < sizeof(T); ++k)
				first[i * sizeof(T) + k] = ures[k];
		}

		return first;
	}

	template<typename T>
	bsoncxx::types::b_binary parseVectorToBinary(
		const std::vector<T>& vector
	) {
		// Set into bin_data obj and return
		bsoncxx::types::b_binary bin_data = {};
		bin_data.bytes = parseVectorToBinary(vector, bin_data.size);
		return bin_data;
	}

	void makeFeed(
		const int account_id,
		const int abstraction_value,
		const int amount,
		const std::string index_name,
		std::vector<int>& post_results
	) {
		// Get account-activities
		std::vector<int> his_post_ids, his_vote_ids;
		User::Account::getActivities(account_id, his_post_ids, his_vote_ids);
		const int max_account_activities = his_post_ids.size() + his_vote_ids.size();
		if (max_account_activities == 0)
			return; // Nothing available

		// Insert all activities into one set to remove them from post_scores
		std::set<int> account_activities(his_post_ids.begin(), his_post_ids.end());
		account_activities.insert(his_vote_ids.begin(), his_vote_ids.end());

		// Establish connection
		auto client = GLOBAL::MongoDB::mongoPool.acquire();
		auto post_data = (*client)["hive-discover"]["post_data"];

		std::srand(std::time(nullptr));
		std::map<int, int> post_distances; // post-id and number (from highToLowFunction)
		size_t loop_counter = 0;

		// Get distances while not enough posts are got (double amount to get more randomness) or the loop counter reaches 250
		while (post_distances.size() < (amount * 2) && loop_counter < 250) {
			// Find random indexes for post_ids and vote_ids
			std::set<int> rndIndexes;
			while(rndIndexes.size() < max_account_activities && rndIndexes.size() < MAX_POSTS_FOR_FEED)
				rndIndexes.insert(std::rand() % max_account_activities);

			// Get categories of random selected posts	
			//	Convert rndIndexes to bsoncxx::array of ids
			bsoncxx::builder::basic::array post_ids;
			for (const int i : rndIndexes) {
				if (i < his_post_ids.size())
					post_ids.append(his_post_ids[i]);
				else
					post_ids.append(his_vote_ids[i - his_post_ids.size()]);
			}
			
			//	Get Cursor and doc-vectors of selected posts
			std::map<std::string, std::vector<std::vector<float>>> lang_doc_vectors; //lang, list of doc-vectors
			auto cursor = post_data.find(
				make_document(
					kvp("_id", make_document(kvp("$in", post_ids))),
					kvp("doc_vectors", make_document(kvp("$exists", true))),
					kvp("doc_vectors", make_document(kvp("$ne", NULL)))
				)
			);

			for (const auto& post_doc : cursor) {
				// Get all doc-vectors of voted/posted content
				try {
					const bsoncxx::document::view doc_vectors = post_doc["doc_vectors"].get_document().value;
					std::vector<float> vec = {};

					for (const auto& pair : doc_vectors) {
						// Binary to vector
						parseBinaryToVector<float>(pair, vec);
						std::string current_lang = pair.key().to_string();

						// Add to map
						if (!lang_doc_vectors.count(current_lang))
							lang_doc_vectors[current_lang] = {};
						lang_doc_vectors[current_lang].push_back(vec);
					}
				}catch (std::exception ex) {
					std::cout << "[ERROR] Cannot get the doc-vectors for this post: " << std::to_string(post_doc["_id"].get_int32().value) << std::endl;
				}
			}

			// Get similar posts for each lang
			std::vector<knn_result_t> similar_result;
			for(const auto& lang_query : lang_doc_vectors)
				Categories::getSimilarPostsByDocVector(index_name, lang_query.first, lang_query.second, abstraction_value + loop_counter + 3, similar_result);

			// Insert all of them into post_scores (lowest distance is the best) when the post is not inside account_activities
			for (knn_result_t& result : similar_result) {
				while (!result.empty()) {
					const auto elem = result.top();
					result.pop();

					if (account_activities.count(elem.second))
						continue; // Is his own vote/comment

					// Push distance to map by inverting high to low values
					if (!post_distances.count(elem.second))
						post_distances[elem.second] = 0;
					
					post_distances[elem.second] += highToLowFunc(elem.first); 
				}
			}

			++loop_counter;
		}
		
		// Roulette Randomness
		//	- Prepare Wheel
		std::map<int, int> wheel_plate; // plates for this _id, post_id
		int total = 0;
		for (const auto& p_dis : post_distances) {			
			for(int i = 0; i < p_dis.second; ++i, ++total)
				wheel_plate[total] = p_dis.first;
		}

		// Get set with post_ids and size of the amount
		std::set<int> ids_set;
		while (ids_set.size() < amount) {
			const int rnd_x = std::rand() % total;
			if (wheel_plate.count(rnd_x))
				ids_set.insert(wheel_plate[rnd_x]);
		}

		// Fill post_results with that set
		post_results.reserve(post_results.size() + amount);
		for (const int& _id : ids_set)
			post_results.push_back(_id);
	}


	int start() {	
		// Start API
		Listener::startAPI();

		// Threads for Index Builds and sub-methods
		//	* Post Category Index
		std::atomic<bool> category_index_ready(false);
		std::thread category_indexer_task([&category_index_ready]() {
			// Build Index and wait 15 Minutes to rebuild it

			while (1) {
				Categories::buildIndexes(!category_index_ready); // Do all in_parralel to increase startup speed
				category_index_ready = true;

				std::this_thread::sleep_for(std::chrono::minutes(15)); 
			}
		}); 

		//	* Account Interests Index
		std::atomic<bool> account_index_ready(false);
		std::thread account_indexer_task([&account_index_ready]() {
			// Build Index, then wait one Hour and finally rebuild ALL profiles (long and intense calculation), that 
			// is why we first wait and then do it because on startup we need performance for other ressources...

			while (1) {
				Accounts::buildIndex();
				account_index_ready = true;

				std::this_thread::sleep_for(std::chrono::hours(1));

				if(GLOBAL::isPrimary) // Only primary task
					Accounts::set_all_account_profiles();
			}		
		});

		// Check when the Server is ready
		{
			while (!category_index_ready || !account_index_ready)
				std::this_thread::sleep_for(std::chrono::milliseconds(25));

			// Indexes all build
			GLOBAL::SERVER_IS_READY = true;
		}

		category_indexer_task.join();
		account_indexer_task.join();
		return 0;
	}


	namespace Categories {

		std::map<std::string, std::map<std::string, index_t>> ALL_INDEXES = {};

		void buildOneIndexName(
			const std::string index_name, 
			const std::string id_source, 
			const std::string& query
		) {
			// Create client, get matching ids and then the cursor			
			bsoncxx::builder::basic::array post_ids;
			mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
			{
				// Settings for finding				
				auto col_post_data = (*client)["hive-discover"]["post_data"];
				mongocxx::options::find opts;
				opts.projection(make_document(kvp("_id", 1)));
				auto source_col = (*client)["hive-discover"][id_source];		
				
				// Get all ids
				for (const auto& doc : source_col.find(bsoncxx::from_json(query), opts))
					post_ids.append(doc["_id"].get_int32().value);
			}
			
			// Index-Building-Task Definition
			const auto worker_task = [&post_ids, index_name](const std::string lang)->index_t {
				// Get cursor for post_data	with elements from this lang
				mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
				auto col_post_data = (*client)["hive-discover"]["post_data"];
				mongocxx::cursor cursor = col_post_data.find(
					make_document(
						kvp("_id", make_document(kvp("$in", post_ids))),
						kvp("doc_vectors." + lang, make_document(kvp("$exists", true)))
					)
				);

				// Init AlgorithmInterface
				size_t alg_ifcCapacity = 100;
				index_t current_index = index_t(
					new hnswlib::HierarchicalNSW<float>(&space300, alg_ifcCapacity)
				);

				// Process all docs
				size_t elementCounter = 0;
				std::vector<float> vec = {};
				for (auto& doc : cursor) {
					// Parse binary form of doc_vectors to a std::vector<float>
					parseBinaryToVector<float>(doc["doc_vectors"][lang], vec);
					if (vec.size() != 300)
						continue; // Some error <=> Do not enter this

					// Add item to index
					hnswlib::labeltype _id = doc["_id"].get_int32().value;
					current_index->addPoint(vec.data(), _id);

					// Resize AlgorithmInterface
					++elementCounter;
					if (elementCounter >= alg_ifcCapacity) {
						alg_ifcCapacity += 100;
						static_cast<hnswlib::HierarchicalNSW<float>*>(current_index.get())->resizeIndex(alg_ifcCapacity);
					}
				}

				if (elementCounter <= 100) {
					// To less elements
					std::cout << "[INFO] Skipped entering a new doc-vectors-index named " << index_name << " for " << lang << "-posts because of only " << elementCounter << " available elements" << std::endl;
					return nullptr;
				}

				std::cout << "[INFO] Successfully build a new doc-vectors-index named " << index_name << " for " << lang << "-posts with " << elementCounter << " elements" << std::endl;
				return current_index;
			};

			// Start index-building-task for each lang
			std::map<std::string, std::future<index_t>> lang_tasks;
			const std::vector<std::string> lang_cols = (*client)["fasttext"].list_collection_names();
			for (const std::string lang : lang_cols) {
				lang_tasks.emplace(std::pair<std::string, std::future<index_t>>(lang, std::async(worker_task, lang)));
			}

			// Wait for tasks to finish and set to global map
			std::map<std::string, index_t> lang_indexes;
			for (auto& l_task : lang_tasks) {
				l_task.second.wait();
				lang_indexes[l_task.first] = l_task.second.get();
			}
				
			ALL_INDEXES[index_name] = lang_indexes;
		}

		void buildIndexes(bool in_parralel)
		{
			// Establish connections and get all index templates
			std::vector<std::tuple<std::string, std::string, std::string>> indexname_target_query; // index-name, target collection and query on target collection
			{
				mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
				auto col_knn_categories_index = (*client)["hive-discover"]["knn_categories_index"];
				for (const auto& definition : col_knn_categories_index.find({})) {
					const std::string elem_name = definition["name"].get_utf8().value.to_string();
					const std::string elem_target_col = definition["target_col"].get_utf8().value.to_string();
					const auto elem_query = definition["query"].get_document().value;
					const int elem_minus_days = definition["minus_days"].get_int32().value; 
					
					// Build query-doc
					bsoncxx::builder::basic::document post_data_query{};
					for (auto& d : elem_query)
						post_data_query.append(kvp(d.key(), d.get_value()));

					// Set minusDays
					bsoncxx::types::b_date minDate = bsoncxx::types::b_date(std::chrono::system_clock::now() - std::chrono::hours{ elem_minus_days * 24 });
					post_data_query.append(kvp("timestamp", make_document(kvp("$gt", minDate))));	

					indexname_target_query.push_back(
						std::tuple<std::string, std::string, std::string>(elem_name, elem_target_col, bsoncxx::to_json(post_data_query.extract()))
					);
				}

			}
			
			// Build all of them
			if (in_parralel) {
				// Build all in parralel (high-intense CPU and Network Operation
				std::vector<std::thread> workers;
				for (auto& definition : indexname_target_query)
					workers.push_back(std::thread(buildOneIndexName, std::get<0>(definition), std::get<1>(definition), std::get<2>(definition)));

				// Wait for them
				for (auto& th : workers)
					th.join();
			}
			else {
				// Build one by one (relax CPU and Network)
				for (auto& definition : indexname_target_query)
					buildOneIndexName(std::get<0>(definition), std::get<1>(definition), std::get<2>(definition));
			}
		}

		void getSimilarPostsByDocVector(
			std::string index_name, 
			std::string lang,
			const std::vector<std::vector<float>>& queries,
			const int k,
			std::vector<knn_result_t>& results	
		) {
			// Get Index-Name
			if (!ALL_INDEXES.count(index_name)) 
				index_name = DEFAULT_INDEX_NAME; // Index does not exist ==> use default one
			if (!ALL_INDEXES.count(index_name))
				return; // No index exists (maybe not yet) ==> just abort

			// Get Index-Lang
			if (!ALL_INDEXES[index_name].count(lang))
				lang = DEFAULT_LANG; // Lang does not exist ==> use default one
			if (!ALL_INDEXES[index_name].count(lang) || !ALL_INDEXES[index_name][lang])
				return; // maybe nullptr <=> Not enough posts for this lang

			// Sure, we got our index ==> do KNN-Search
			const index_t index = ALL_INDEXES[index_name][lang];
			for (const auto& q : queries) 
				results.push_back(index->searchKnn(q.data(), k));		
		}

		void getSimilarPostsByDocVector(
			std::string index_name,
			std::string lang,
			const std::vector<std::vector<float>>& queries,
			const int k,
			std::vector<std::vector<int>>& results
		) {
			// Get priority Queue
			std::vector<knn_result_t> r_priority_queue;
			getSimilarPostsByDocVector(index_name, lang, queries, k, r_priority_queue);

			// Convert priority queue into vector (remove distance)
			for (knn_result_t& r_knn : r_priority_queue) {
				std::vector<int> r_ids;

				// Get element from queue and push id of it
				while (!r_knn.empty()) {						
					r_ids.push_back(r_knn.top().second);
					r_knn.pop();
				}

				results.push_back(r_ids);
			}
		}
	}

	namespace Accounts {
		std::map<std::string, index_t> ALL_INDEXES = {}; // index for each (available) lang
		index_t productionIndex = nullptr;

		std::map<std::string, std::vector<float>> calc_account_profile(const int account_id) {
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
			mongocxx::options::find opts;
			opts.projection(make_document(kvp("doc_vectors", 1)));
			auto cursor = post_data.find(
				make_document(
					kvp("_id", make_document(kvp("$in", activity_ids))),
					kvp("doc_vectors", make_document(kvp("$exists", true)))
			), opts);

			// Enter activities for each lang
			std::map<std::string, std::vector<float>> vector_per_lang;
			std::map<std::string, int> vector_per_lang_counter;
			int total_posts = 0; // Count of posts (multilingual and nolingual posts count also as 1)

			std::vector<float> current_vec;
			for (const auto& post_doc : cursor) {
				// Iterate throug every lang of this post
				total_posts += 1;
				const bsoncxx::document::view doc_vectors = post_doc["doc_vectors"].get_document().value;
				for (const auto& pair : doc_vectors) {
					// Parse pair to vector<float> and string
					parseBinaryToVector<float>(pair, current_vec);
					std::string current_lang = pair.key().to_string();

					if (!vector_per_lang.count(current_lang)) {
						// First vector of this lang
						vector_per_lang[current_lang] = std::vector<float>(300);
						vector_per_lang_counter[current_lang] = 0;
					}

					// Add element-wise (directly as an average)
					auto doc_it = current_vec.begin();
					for (auto lang_it = vector_per_lang[current_lang].begin(); lang_it != vector_per_lang[current_lang].end(); ++lang_it, ++doc_it)
						*lang_it = (*lang_it + * doc_it) / 2;

					vector_per_lang_counter[current_lang] += 1;
				}
			}

			// Ensure to have at least 35% of the languages
			for (const auto& lang_counter : vector_per_lang_counter) {
				if ((lang_counter.second / total_posts) < 0.35) // Then remove lang-item
					vector_per_lang.erase(lang_counter.first);
			}

			return vector_per_lang;
		}

		void set_all_account_profiles() {
			const auto t_start = std::chrono::high_resolution_clock::now();

			// Get a connection
			mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
			auto collection = (*client)["hive-discover"]["account_info"];

			// Get all accounts and prepare bulk update storage and lock
			mongocxx::options::find opts;
			opts.projection(make_document(kvp("_id", 1)));
			auto cursor = collection.find({}, opts);

			// Get all account ids
			std::stack<int> all_accounts;
			for (const auto& account_doc : cursor)
				all_accounts.push(account_doc["_id"].get_int32().value);
			const int account_count = all_accounts.size();
			
			// Bulk Settings
			mongocxx::options::bulk_write bulkWriteOption;
			bulkWriteOption.ordered(false);
			const int BULK_SIZE = 5;
			auto bulk_enter_task = std::async([]() {return true; }); // Create dummy task

			while (all_accounts.size()) {
				std::map<int, std::future<std::map<std::string, std::vector<float>>>> account_results; // id, result-future

				// Fill results with tasks until max reaches or no accounts left
				while (all_accounts.size() && account_results.size() < BULK_SIZE) {
					const int acc_id = all_accounts.top();
					account_results[acc_id] = std::async(calc_account_profile, acc_id);
					all_accounts.pop();
				}

				// Create bulk-operation and append results
				// Shared Ptr because we later have to give it to a lambda function and by so, we do not have to copy it
				size_t bulk_counter = 0;
				std::shared_ptr<mongocxx::bulk_write> bulk = std::make_shared<mongocxx::bulk_write>(
					collection.create_bulk_write(bulkWriteOption)
				);

				for (auto& result_pair : account_results) {
					// Convert map to object and add bulk-update-model
					// lang_vector : [lang, vector]
					for (const auto& lang_vector : result_pair.second.get()) {
						// Convert vector to binary and document for update
						bsoncxx::types::b_binary bin_data{};
						bin_data.bytes = parseVectorToBinary(lang_vector.second, bin_data.size);

						//all_bin_data.push_back(bin_data);
						bsoncxx::document::value update_doc = make_document(
							kvp("interests." + lang_vector.first, bin_data)
						);

						// Create Bulk-Model and append it
						const auto update_model = mongocxx::model::update_one(
							make_document(kvp("_id", result_pair.first)), // Filter
							make_document(kvp("$set", update_doc)) // Update
						);
						bulk->append(update_model);
						++bulk_counter;

						// Deallocate Memory (it was copied inside the update_one-model)
						delete[] bin_data.bytes;
					}
				}

				if (bulk_counter == 0)
					continue; // No bulk has to be written

				// Wait for last entering to have surely completed his task
				bulk_enter_task.get();

				// Restart task and redo whole loop
				bulk_enter_task = std::async([bulk]() {
					try {
						// Perform bulk-update
						bulk->execute();
					}
					catch (std::exception ex) {
						std::cout << "[ERROR] Exception raised at set_all_account_profiles(): " << ex.what() << std::endl;
					}

					return true;
				});
			}

			// Wait for the last task to finish as well
			bulk_enter_task.get();

			const auto t_end = std::chrono::high_resolution_clock::now();
			const double elapsed_time_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();
			const double elapsed_time_min = elapsed_time_ms / (1000 * 60); // 1min = 60sec = 6000ms | 1000ms = 1s
			std::cout << "[INFO] Rebuild all " << account_count << " account interests in " << elapsed_time_min << " minutes." << std::endl;
		}

		void buildIndex() {
			// Establish connection and prepare query
			mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
			auto collection = (*client)["hive-discover"]["account_info"];
			auto cursor = collection.find(make_document(
				kvp("interests", make_document(kvp("$exists", true)))
			));

			std::map<std::string, index_t> lang_indexes; // index for each lang
			std::map<std::string, int> lang_counter; // counter for each lang items
			std::map<std::string, int> lang_index_capacities; // capacities for each lang index

			// Enter all interests in all lang-indexes
			std::vector<float> vec;
			for (const auto& account_doc : cursor) {
				const int acc_id = account_doc["_id"].get_int32().value;
				const bsoncxx::document::view acc_interests = account_doc["interests"].get_document().value;

				// Iterate through all of his langs
				for (const auto& lang_bindata : acc_interests) {
					// Binary to vector
					parseBinaryToVector<float>(lang_bindata, vec);
					std::string current_lang = lang_bindata.key().to_string();

					if (!lang_counter.count(current_lang)) {
						// First item of that lang ==> create counter, alg_capacity and init index
						lang_counter[current_lang] = 0;
						lang_index_capacities[current_lang] = 100;
						lang_indexes[current_lang] = std::shared_ptr<hnswlib::AlgorithmInterface<float>>(
							new hnswlib::HierarchicalNSW<float>(&space300, lang_index_capacities[current_lang])
						);
					}

					// Add to this index
					lang_counter[current_lang] += 1;
					if (lang_counter[current_lang] >= lang_index_capacities[current_lang]) {
						// Resize Index
						lang_index_capacities[current_lang] += 10;
						static_cast<hnswlib::HierarchicalNSW<float>*>(lang_indexes[current_lang].get())->resizeIndex(lang_index_capacities[current_lang]);
					}
					lang_indexes[current_lang]->addPoint(vec.data(), acc_id);
				}
			}

			// Keep only indexes with at least 100 accounts
			for (const auto& lang_counting : lang_counter) {
				if (lang_counting.second < 100) // Remove it
					lang_indexes.erase(lang_counting.first);
			}

			// Finally push it to production
			ALL_INDEXES = lang_indexes;
			std::cout << "[INFO] Created all Account-Indexes: " << std::endl;
			for(const auto& lang_idx : lang_indexes) 
				std::cout << "	- " << lang_idx.first << "-index with " << lang_counter[lang_idx.first] << " elements" << std::endl;
		}

		void getSimilarAccounts(
			const std::map<std::string, std::vector<float>>& query,
			const int k,
			std::map<std::string, knn_result_t>& result
		) {
			// Copy indexes
			auto indexes = ALL_INDEXES;

			for (auto& lang_q : query) {
				if (!indexes.count(lang_q.first))
					continue; // Lang and Index not available

				// Do Search
				result[lang_q.first] = indexes[lang_q.first]->searchKnn(lang_q.second.data(), k);
			}			
		}
	}
	
}