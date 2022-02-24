#include "ImageAPI/searching.h"

#include <bsoncxx/builder/basic/document.hpp>
#include <bsoncxx/builder/basic/kvp.hpp>
#include "main.h"
#include <mongocxx/client.hpp>
#include <mongocxx/pool.hpp>
#include <thread>
#include <vector>

#define e(n) pow(10,n)

using bsoncxx::builder::basic::kvp;
using bsoncxx::builder::basic::make_document;
namespace ImageAPI {

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

	namespace ImgSearch {
		index_t producton_index = nullptr;

		void buildIndex() {
			// Init AlgorithmInterface
			size_t alg_ifcCapacity = 1000;
			index_t current_index = index_t(
				new hnswlib::HierarchicalNSW<float>(&space1000, alg_ifcCapacity)
			);

			// Establish Connetion and Cursor to retrieve all data-docs
			mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
			auto col_post_data = (*client)["images"]["img_data"];
			mongocxx::cursor cursor = col_post_data.find({});

			// Enter all post's average image-lpb
			size_t alg_elem_counter = 0;
			std::vector<float> vec;
			for (const auto& data_doc : cursor) {
				if (data_doc["v"].type() != bsoncxx::type::k_binary)
					continue; // Maybe NULL-value

				parseBinaryToVector<float>(data_doc["v"], vec);
				if (vec.size() != 1000 || data_doc["_id"].type() != bsoncxx::type::k_int32)
					continue; // Some error <=> Do not enter this

				// Add item to index
				hnswlib::labeltype _id = data_doc["_id"].get_int32().value;
				current_index->addPoint(vec.data(), _id);

				// Resize AlgorithmInterface
				++alg_elem_counter;
				if (alg_elem_counter >= alg_ifcCapacity) {
					alg_ifcCapacity += 1000;
					static_cast<hnswlib::HierarchicalNSW<float>*>(current_index.get())->resizeIndex(alg_ifcCapacity);
				}
			}

			producton_index = current_index;
			std::cout << "[INFO] Successfully build a new feature-vectors-index for the Image-API with " << alg_elem_counter << " elements." << std::endl;
		}

		void search(
			const std::vector<std::vector<float>>& queries,
			const int k,
			std::vector<std::vector<int>>& results
		) {
			if (producton_index == nullptr)
				return; // Not loaded

			for (const auto& q : queries) {
				// Do kNN Search
				knn_result_t prio_queue = producton_index->searchKnn(q.data(), k);

				// Get elements from queue and push them to results (reversed <=> best was at the last)
				std::vector<int> r_ids(prio_queue.size());
				for (int i = prio_queue.size(); i > 0; --i) {
					r_ids[i - 1] = prio_queue.top().second;
					prio_queue.pop();
				}

				results.push_back(r_ids);
			}
		}

		bsoncxx::builder::basic::array vectorToBsonArray(std::vector<int>::iterator start, std::vector<int>::iterator end) {
			bsoncxx::builder::basic::array arr;
			for (; start != end; ++start)
				arr.append(*start);
			return arr;
		}

		bsoncxx::builder::basic::array VectorToBsonArrayReversed(std::vector<int>::iterator start, std::vector<int>::iterator end) {
			bsoncxx::builder::basic::array arr;
			for (; start != end; --start)
				arr.append(*start);
			return arr;
		}

		void addSimilarImages(const int img_id)
		{
			mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
			auto col_img_data = (*client)["images"]["img_data"];

			// Get Features and Targets of this image
			std::vector<float> features(1000);
			std::vector<int> target_post_ids;
			{
				// Find Image-Document or throw an Error
				const auto maybe_doc = col_img_data.find_one(make_document(kvp("_id", img_id)));
				if (!maybe_doc) 
					throw std::runtime_error("Cannot Find an Image with that id: " + std::to_string(img_id));

				// Get important information: Features and target
				const auto img_doc = maybe_doc.value().view();
				parseBinaryToVector<float>(img_doc["v"], features);
				for (const auto& elem : img_doc["target"].get_array().value)
					target_post_ids.push_back(elem.get_int32().value);
			}
			
			// Find Similar Images with a distance more than eps to ensure that not the exact-same 
			//  (just url changed) images get machted
			std::vector<int> results;
			{
				// k = 100 to have images from other posts as well
				const int k = 100;
				knn_result_t prio_queue = producton_index->searchKnn(features.data(), k);

				// Add items to queue, when they are over/under min/max
				const float min = e(-5), max = e(5);
				while (prio_queue.size()) {
					// Get and remove item
					const auto elem = prio_queue.top();
					prio_queue.pop();

					// Check min/max
					if (elem.first < min || elem.first > max)
						continue; 

					results.push_back(elem.second);
				}
			}

			// Remove img-ids, where their target-ids do occur in "target_post_ids"
			{
				auto cursor = col_img_data.find(
					make_document(
						kvp("_id", make_document(
							kvp("$in", vectorToBsonArray(results.begin(), results.end()))
						)
						),
						kvp("target", make_document(
							kvp("$in", vectorToBsonArray(target_post_ids.begin(), target_post_ids.end()))
						)
						)
					)
				);
				for (const auto& doc : cursor) {
					// Remove this img-id
					const int current_id = doc["_id"].get_int32().value;
					auto it = results.begin();
					for (; it != results.end(), *it != current_id; ++it)
						continue; // Iterate to the end or to the item; delete when is the item

					if (it != results.end()) // Delete, when its not the end
						results.erase(it);
				}
			}


			// the last ones are the best ==> get iterator to the 9th best elem
			auto result_it = results.begin();
			if (results.size() >= 9)
				result_it += results.size() - 9;
					
			col_img_data.update_one(
				make_document(kvp("_id", img_id)), // Filter
				make_document(kvp("$set", // Update
					make_document(
						kvp("sim", VectorToBsonArrayReversed(results.end() - 1, result_it - 1))
					)
				)) 
			);
		}

		void calcAllSimilarities() {
			mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
			auto col_img_data = (*client)["images"]["img_data"];
			mongocxx::options::find find_op;
			find_op.projection(make_document(kvp("_id", 1)));

			// Get all img-Ids
			std::queue<int> img_ids;
			for (const auto& doc : col_img_data.find({}, find_op))
				img_ids.push(doc["_id"].get_int32().value);

			// Run them all into 4 concurrent mini-threads
			while (img_ids.size()) {
				// Start Worker-Thread with current img-id and pop id
				std::vector<std::thread> workers;
				for (int i = 0; i < 12 && img_ids.size() > 0; ++i) {
					workers.emplace_back(std::thread(addSimilarImages, img_ids.front()));
					img_ids.pop();
				}

				// Wait for all of them to finish
				for (auto& th : workers) {
					if(th.joinable());
						th.join();
				}

				continue;
			}

			std::cout << "[INFO] Calculated Similar Images" << std::endl;
		}

		void calcNewImgsSimilartities() {
			// Establish Connection and prepare the Cursor
			mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
			auto col_img_data = (*client)["images"]["img_data"];
			auto cursor = col_img_data.find(make_document(kvp("sim", make_document(kvp("$exists", false)))));

			// Go through the cursor and calc similarities
			std::queue<std::thread> workers; // max. 4 concurrent threads
			size_t counter = 0;
			for (const auto& doc : cursor) {
				const int post_id = doc["_id"].get_int32().value;

				// Wait, when (more than) 4 workers are working
				if (workers.size() >= 4) {
					// Join and Dequeue Thread
					workers.front().join();
					workers.pop();
				}
			
				// Add task
				workers.push(std::thread(addSimilarImages, post_id));
				counter += 1;
			}

			// Wait for rest of workers
			while (workers.size()) {
				workers.front().join();
				workers.pop();
			}

			std::cout << "[INFO] Calced similarites for " << counter << " images" << std::endl;
		}
	}

	void runBuildAgent() {
		// Wait pre-delay (API is up and responding 307-Code to other instances)
		if (GLOBAL::PRE_DELAY > 0) {
			std::cout << "[INFO] Waiting " << GLOBAL::PRE_DELAY << "s before starting..." << std::endl;
			std::this_thread::sleep_for(std::chrono::seconds(GLOBAL::PRE_DELAY));
		}

		std::atomic<bool> indexes_ready(false);
		std::thread searchTask([&indexes_ready]() {
			// Build and Wait 3 Hours 5 Min
			while (1) {
				ImgSearch::buildIndex();
				indexes_ready = true;

				// Wait 10 Min
				std::this_thread::sleep_for(std::chrono::minutes(10));
			}
		});

		std::thread similarTask([&indexes_ready]() {
			// Job for the primary node only
			if (GLOBAL::isPrimary == false) return;

			// Wait for the Image-Index to be ready
			while (indexes_ready == false)
				std::this_thread::sleep_for(std::chrono::minutes(1));

			while (1) {
				// Run every 5 Minutes the Sim-Job for new Images
				// Do this 36 times (total: 3h) and then run Sim-Job for all Images
				for (size_t i = 0; i < 36; ++i) {
					ImgSearch::calcNewImgsSimilartities();
					std::this_thread::sleep_for(std::chrono::minutes(5));
				}

				ImgSearch::calcAllSimilarities();
			}
		});

		// Check when the Server is ready
		{
			while (!indexes_ready)
				std::this_thread::sleep_for(std::chrono::milliseconds(25));

			// Indexes all build
			GLOBAL::SERVER_IS_READY = true;
		}

		searchTask.join();
		similarTask.join();
	}
}