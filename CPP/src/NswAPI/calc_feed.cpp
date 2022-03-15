#include "NswAPI/calc_feed.h"

#include <bsoncxx/builder/basic/document.hpp>
#include <bsoncxx/builder/basic/kvp.hpp>
#include <bsoncxx/json.hpp>
#include "NswAPI/index.h"
#include "main.h"
#include <math.h>
#include <mongocxx/bulk_write.hpp>
#include <mongocxx/client.hpp>
#include <mongocxx/pool.hpp>
#include <mongocxx/model/update_one.hpp>
#include "User/account.h"

using bsoncxx::builder::basic::kvp;
using bsoncxx::builder::basic::make_document;
using bsoncxx::builder::basic::make_array;

namespace NswAPI {

	template<typename T>
	inline bsoncxx::builder::basic::array setToBsonArray(const std::set<T>& s) {
		bsoncxx::builder::basic::array arr;
		for (const T& item : s)
			arr.append(item);
		return arr;
	}

	namespace parsing {
		template<typename T>
		inline void parseBinaryToVector(
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
		inline void parseBinaryToVector(
			const bsoncxx::document::element& binary_element,
			std::vector<T>& result
		) {
			const bsoncxx::types::b_binary bin_data = binary_element.get_binary();
			parseBinaryToVector<T>(bin_data.bytes, bin_data.size, result);
		}
	}
	

	namespace calcFeed {

		void get_docvectors(
			const bsoncxx::builder::basic::array& post_ids,
			std::map<std::string, std::vector<std::vector<float>>>& doc_vectors
		) {
			// Establish connection
			auto client = GLOBAL::MongoDB::mongoPool.acquire();
			auto post_data = (*client)["hive-discover"]["post_data"];

			// Get a cursor of selected elements 
			auto cursor = post_data.find(
				make_document(
					kvp("_id", make_document(kvp("$in", post_ids))),
					kvp("doc_vectors", make_document(kvp("$exists", true))),
					kvp("doc_vectors", make_document(kvp("$ne", NULL)))
				)
			);

			// Retrieve documents, parse and push doc-vectors
			std::vector<float> current_vector;
			for (const auto& doc : cursor) {
				if (!doc["doc_vectors"] || doc["doc_vectors"].type() != bsoncxx::type::k_document)
					continue;

				try {
					// Try to parse
					for (const auto& pair : doc["doc_vectors"].get_document().value) {
						std::string current_lang = pair.key().to_string();

						// Binary to vector and add to map
						parsing::parseBinaryToVector<float>(pair, current_vector);
						if (!doc_vectors.count(current_lang))
							doc_vectors[current_lang] = {};
						doc_vectors[current_lang].push_back(current_vector);
					}
				}
				catch (std::exception ex) {
					// Parsing failed ==> just skip
					std::cout << "[ERROR] Cannot get the doc-vectors for this post: " << std::to_string(doc["_id"].get_int32().value) << std::endl;
				}
			}
		}

		void get_docvectors(
			const bsoncxx::builder::basic::array& post_ids,
			std::map<std::string, std::vector<std::pair<int, std::vector<float>>>>& doc_vectors
		) {
			// Establish connection
			auto client = GLOBAL::MongoDB::mongoPool.acquire();
			auto post_data = (*client)["hive-discover"]["post_data"];

			// Get a cursor of selected elements 
			auto cursor = post_data.find(
				make_document(
					kvp("_id", make_document(kvp("$in", post_ids))),
					kvp("doc_vectors", make_document(kvp("$exists", true))),
					kvp("doc_vectors", make_document(kvp("$ne", NULL)))
				)
			);

			// Retrieve documents, parse and push doc-vectors
			std::vector<float> current_vector;
			for (const auto& doc : cursor) {
				const int post_id = doc["_id"].get_int32().value;
				if (!doc["doc_vectors"] || doc["doc_vectors"].type() != bsoncxx::type::k_document)
					continue;

				try {
					// Try to parse
					for (const auto& pair : doc["doc_vectors"].get_document().value) {
						std::string current_lang = pair.key().to_string();

						// Binary to vector and add to map
						parsing::parseBinaryToVector<float>(pair, current_vector);
						if (!doc_vectors.count(current_lang))
							doc_vectors[current_lang] = {};
						doc_vectors[current_lang].push_back(std::pair<int, std::vector<float>>(post_id, current_vector));
					}
				}
				catch (std::exception ex) {
					// Parsing failed ==> just skip
					std::cout << "[ERROR] Cannot get the doc-vectors for this post: " << std::to_string(doc["_id"].get_int32().value) << std::endl;
				}
			}
		}

		void get_sample(
			const std::vector<int>& his_post_ids,
			const std::vector<int>& his_vote_ids,
			const int amount,
			std::map<std::string, std::vector<std::vector<float>>>& sample
		) {
			std::srand(std::time(nullptr));
			const size_t total_count = his_post_ids.size() + his_vote_ids.size();

			// Get random indexes to select sample ids
			std::set<int> rnd_indexes;
			while (rnd_indexes.size() < amount && rnd_indexes.size() < total_count)
				rnd_indexes.insert(std::rand() % total_count);

			// Build bson::array of selected ids
			bsoncxx::builder::basic::array post_ids;
			for (const int i : rnd_indexes) {
				if (i < his_post_ids.size())
					post_ids.append(his_post_ids[i]);
				else
					post_ids.append(his_vote_ids[i - his_post_ids.size()]);
			}

			// Get and return doc-vectors
			get_docvectors(post_ids, sample);
		}

		void find_similar(
			const std::map<std::string, std::vector<std::vector<float>>>& input,
			const std::string index_name,
			const size_t k,
			std::set<int>& similar_ids,
			const std::set<int> filter_out
		) {
			std::vector<knn_result_t> similar_result;

			// do kNN-Search for each entry
			for (auto it = input.begin(); it != input.end(); ++it) {
				Categories::getSimilarPostsByDocVector(
					index_name, 
					it->first, // lang
					it->second, // doc-vectors as vector in a vector
					k, 
					similar_result
				);
			}

			// flatten the similar_result and just add the ids
			int post_id = 0;
			for (auto& r : similar_result) {
				while (r.size()) {
					// Get Post id and remove it from the queue
					post_id = r.top().second;
					r.pop();

					// Check filter out, else add it
					if (!filter_out.count(post_id))
						similar_ids.insert(post_id);
				}
			}
		}

		void calc_sim_scores(
			const std::map<std::string, std::vector<std::pair<int, std::vector<float>>>>& similar_doc_vectors,
			const std::map<std::string, std::vector<std::vector<float>>>& sample_doc_vectors,
			std::map<float, int>& sim_scores
		) {
			for (const auto& sim_lang : similar_doc_vectors) {
				// Check if lang occurs in sample
				const std::string& lang = sim_lang.first;
				if (!sample_doc_vectors.count(lang))
					continue;
				const std::vector<std::vector<float>>& sample_vectors = sample_doc_vectors.at(lang);

				// Calc cosine-sim for each similar post and all sample posts
				for (const std::pair<int, std::vector<float>>& sim_pair : sim_lang.second) {
					const std::vector<float>& sim_vec = sim_pair.second;

					// Get total sim score
					float total_sim_score = 0;
					for (const std::vector<float>& sample_vec : sample_vectors) {
						// Calc Cosine-Similarity for each sample
						float dot = 0.0, denom_a = 0.0, denom_b = 0.0;
						for (unsigned int i = 0u; i < sample_vec.size(); ++i) {
							dot += sample_vec[i] * sim_vec[i];
							denom_a += sample_vec[i] * sample_vec[i];
							denom_b += sim_vec[i] * sim_vec[i];
						}

						// Add sim-score to total
						total_sim_score += dot / (sqrt(denom_a) * sqrt(denom_b));
					}

					// Enter total-score in sim_scores 
					sim_scores[total_sim_score] = sim_pair.first;
				}
			}
		}

		void sample_similar_weighted(
			const std::map<float, int>& sim_ids,
			const int amount,
			std::vector<int>& result
		) {
			// We do not want to just select the best ones, instead the best ones should just have a higher probability to get choosen and returned
			// This procedure is called weighted/wheel of fortune/roulette randomness and well described over the net. But instead of a wheel, we use
			// the exponential distribution to choose random but with weights efficiently. It is described in the following Stack Overflow Comment:
			// https://stackoverflow.com/a/65207342/7586306

			int smallest_id = 0;
			float smallest_z = 0, z = 0;
			float smallest_val = 0;

			while (result.size() < amount && result.size() < sim_ids.size()) {
				// Init 0-value
				smallest_id = 0;
				smallest_z = INT_MAX;

				for (const auto& sim_pair : sim_ids) {
					z = -(log(1 - static_cast <float> (rand()) / static_cast <float> (RAND_MAX))) / (sim_pair.first / 1000);
					if (z < smallest_z) {
						smallest_id = sim_pair.second;
						smallest_val = sim_pair.first;
						smallest_z = z;
					}
				}

				// Insert in result
				result.push_back(smallest_id);
				// Removing this item from the sim-map would make theoretically sense, but 
				// practically it is rare that this item comes again so we can ignore this case and save some calculations.
				// The same goals for checking if this item is already in result
			}
		}

	}

	void getFeed(
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
		
		// Get a sample of his activies
		std::map<std::string, std::vector<std::vector<float>>> sample = {}; // lang, doc_vectors 
		calcFeed::get_sample(his_post_ids, his_vote_ids, calcFeed::MAX_POSTS_FOR_FEED, sample);

		// Find similar ids and filter account_activies directly out
		std::set<int> similar_ids = {};
		calcFeed::find_similar(sample, index_name, abstraction_value + 3, similar_ids, account_activities);

		// Get doc-vectors of similar posts
		std::map<std::string, std::vector<std::pair<int, std::vector<float>>>> similar_doc_vectors; // lang, post-id, doc_vectors 
		calcFeed::get_docvectors(setToBsonArray<int>(similar_ids), similar_doc_vectors);

		// Calc cosine sim-scores
		std::map<float, int> sim_scores; // total sim-score, similar post-id
		calcFeed::calc_sim_scores(similar_doc_vectors, sample, sim_scores);
	
		// Get random ones (but weighted by their sim-score)
		calcFeed::sample_similar_weighted(sim_scores, amount, post_results);
	}

}