#include "ImageAPI/listener.h"

#include <bsoncxx/builder/basic/document.hpp>
#include <bsoncxx/builder/basic/kvp.hpp>
#include <bsoncxx/document/view.hpp>
#include <bsoncxx/json.hpp>
#include <boost/algorithm/string.hpp>
#include "main.h"
#include <mongocxx/client.hpp>
#include "ImageAPI/searching.h"
#include "Others/base64.h"
#include <thread>
#include <set>
#include <vector>

using bsoncxx::builder::basic::kvp;
using bsoncxx::builder::basic::make_document;
using bsoncxx::builder::basic::make_array;

namespace ImageAPI {

	std::vector<std::string> tokenizer(const std::string& p_pcstStr, char delim) {
		std::vector<std::string> tokens;
		std::stringstream mySstream(p_pcstStr);
		std::string temp;

		while (getline(mySstream, temp, delim))
			tokens.push_back(temp);

		return tokens;
	}

	// HEADER FILE DEFINITIONS

	int start() {
		std::thread index_builder(runBuildAgent);
		std::thread listener_runner(Listener::runAPI);

		index_builder.join();
		listener_runner.join();
		return 0;
	}

	namespace Listener {

		void defineRoutes() {
			using namespace Endpoints;
			server.resource["^/$"]["POST"] = index;
			server.resource["^/$"]["GET"] = index;

			server.resource["^/similar-searching$"]["POST"] = similar_searching;
		}

		void runAPI() {
			// Configure Server
			server.config.port = GLOBAL::ImageAPI_Port;
			server.config.address = GLOBAL::Host;
			server.config.thread_pool_size = 5;

			defineRoutes();
			server.start();
		}


		namespace Endpoints {
			// All over POST-Method

			void index(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
				// Server Ready and not shutting down?
				if (Helper::serverIsReady(response, request) == false)	return;

				nlohmann::json resBody;
				resBody["status"] = "ok";
				resBody["ready"] = GLOBAL::SERVER_IS_READY.load();
				Helper::writeJSON(response, resBody);
			}

			void similar_searching(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
				// Server Ready and not shutting down?
				if (Helper::serverIsReady(response, request) == false)	return;

				std::thread([](std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
					nlohmann::json reqBody, resBody;

					try {
						// Parse Body
						Helper::parseBody(request, reqBody);
						if (!reqBody.count("query"))
							throw std::runtime_error("query not found");
						if (!reqBody.count("amount"))
							reqBody["amount"] = 100;

						// amount times 3 because of possible duplicated posts
						const int amount = reqBody["amount"].get<int>() * 3;

						mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();

						// Parse Base64-Encoded String to LBP-Vector<float>
						std::vector<float> lbp_vector = {};
						{
							// Set size and enter all elements
							const std::vector<uint8_t> bytes = Base64::decode(reqBody["query"].get<std::string>());
							const uint32_t b_size = bytes.size();
							lbp_vector.resize(b_size / sizeof(float));

							for (size_t i = 0; i < b_size / sizeof(float); ++i)
								lbp_vector[i] = *(reinterpret_cast<const float*>(bytes.data() + i * sizeof(float)));
						}

						// Searching similar items to query-vector | 
						std::vector<std::vector<int>> knn_res;
						ImgSearch::search({ lbp_vector }, amount, knn_res);

						// Find URLs of image-ids
						std::map<std::string, int> image_urls; // url, img-id, 								
						{
							// Build image-id-Array
							bsoncxx::builder::basic::array all_ids;
							for (const auto& x : knn_res[0])
								all_ids.append(x);

							// Find URLS
							mongocxx::options::find opts{};
							opts.projection(make_document(kvp("url", 1)));
							auto cursor = (*client)["images"]["img_data"].find(make_document(kvp("_id", make_document(kvp("$in", all_ids)))), opts);
							for (const auto& doc : cursor)
								image_urls[doc["url"].get_utf8().value.data()] = doc["_id"].get_int32().value;
						}

						// Find posts of images
						std::map<int, std::set<int>> posts_of_images; // post-id, img-id's		
						{
							// Build URL-Array
							bsoncxx::builder::basic::array all_urls;
							for (const auto& pair : image_urls)
								all_urls.append(pair.first);

							// Find posts
							mongocxx::options::find opts{};
							opts.projection(make_document(kvp("images", 1)));
							auto cursor = (*client)["images"]["post_info"].find(make_document(kvp("images", make_document(kvp("$in", all_urls)))), opts);
							for (const auto& doc : cursor) {
								const int _id = doc["_id"].get_int32().value;
								if (!posts_of_images.count(_id))
									posts_of_images[_id] = {};

								// Iterate through Post-Images
								for (const auto& elem : doc["images"].get_array().value) {
									try {
										const std::string url = elem.get_utf8().value.data();
										if (image_urls.count(url))
											posts_of_images[_id].insert(image_urls[url]);
									}
									catch (std::exception ex) {
										std::cout << "[WARNING] Converting elem to string failed in ImageAPI/listener/similar_image" << std::endl;
									}
								}
							}
								
						}
						
						// Find posts and order them
						std::vector<int> result_posts; // post-ids
						int current_index = 0;
						while (result_posts.size() < amount && current_index < knn_res[0].size()) {
							// Get ID
							const int current_img_id = knn_res[0][current_index];
							++current_index;

							// Check if his post in in result_posts. When his post-id is in posts_of_images, then it is available
							// else it was already entered
							int current_post_id = -1;
							for (const auto& ids_pair : posts_of_images) {
								if (ids_pair.second.count(current_img_id)) {
									// Found it
									current_post_id = ids_pair.first;
									break;
								}
							}

							if (current_post_id >= 0) {
								// Found it
								posts_of_images.erase(current_post_id);
								result_posts.push_back(current_post_id);
							}
						}

						// Build Response
						resBody["status"] = "ok";
						if (result_posts.size())
							resBody["results"] = result_posts; // If something was found
						else
							resBody["results"] = std::vector<float>(); // Nothing was found

						Helper::writeJSON(response, resBody);
					}
					catch (std::exception ex) {
						std::cout << "[ERROR] Exception raised at ImageAPI similar-search: " << ex.what() << std::endl;
						resBody["status"] = "failed";
						resBody["error"] = ex.what();
						Helper::writeJSON(response, resBody, "500");
					}
					}, response, request).detach();
			}
		}
	}

}
