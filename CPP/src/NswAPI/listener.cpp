#include "NswAPI/listener.h"

#include <bsoncxx/builder/basic/document.hpp>
#include <bsoncxx/builder/basic/kvp.hpp>
#include <bsoncxx/json.hpp>
#include "main.h"
#include <mongocxx/client.hpp>
#include <nlohmann/json.hpp>
#include "NswAPI/index.h"
#include <set>

namespace NswAPI {
	namespace Endpoints {
		void index(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
			nlohmann::json resBody;
			resBody["status"] = "ok";
			Helper::writeJSON(response, resBody);
		}

		void feed(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
			std::thread([](std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
				nlohmann::json reqBody, resBody;

				try {
					// Parse request Body			
					Helper::parseBody(request, reqBody);


					// Set variables
					int account_id, amount = 50, abstraction_value = 2;
					if (!reqBody.count("account_id"))
						throw std::runtime_error("account_id not found");
					account_id = reqBody["account_id"].get<int>();
					if (reqBody.count("amount"))
						amount = std::min(250, reqBody["amount"].get<int>());
					if (reqBody.count("abstraction_value"))
						abstraction_value = std::min(100, reqBody["abstraction_value"].get<int>());

					// Get feed
					std::unordered_set<int> post_results;
					NswAPI::makeFeed(account_id, abstraction_value, amount, post_results);

					// Enter feed
					resBody["status"] = "ok";
					resBody["posts"] = {};
					for (auto it = post_results.begin(); it != post_results.end(); ++it)
						resBody["posts"].push_back(*it);

					// Return feed
					Helper::writeJSON(response, resBody);
				}
				catch (std::exception ex) {
					std::cout << "[ERROR] Exception raised at feed-making: " << ex.what() << std::endl;
					resBody["status"] = "failed";
					resBody["error"] = ex.what();
					Helper::writeJSON(response, resBody, "500");
				}
				}, response, request).detach();
		}
	
		void similar_by_category(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
			std::thread([](std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
				nlohmann::json reqBody, resBody;

				try {
					// Parse request Body			
					Helper::parseBody(request, reqBody);

					if (!reqBody.count("category"))
						throw std::runtime_error("category not found");
					if (!reqBody.count("amount"))
						throw std::runtime_error("amount not found");
					size_t amount = reqBody["amount"].get<size_t>();

					// Parse Category-Vector
					std::vector<float> categories;
					for (const auto& item : reqBody["category"].items())
						categories.push_back(item.value().get<float>());

					// Search them
					std::vector<std::vector<int>> results;
					getSimilarPostsByCategory({ categories }, amount, results);

					// Return Ids
					resBody["status"] = "ok";
					resBody["posts"] = {};
					if (results.size()) {
						// We got a result
						for (size_t i = 0; i < results[0].size(); ++i)
							resBody["posts"][std::to_string(i)] = results[0][i];
					}
					

					Helper::writeJSON(response, resBody);
				}
				catch (std::exception ex) {
					std::cout << "[ERROR] Exception raised at feed-making: " << ex.what() << std::endl;
					resBody["status"] = "failed";
					resBody["error"] = ex.what();
					Helper::writeJSON(response, resBody, "500");
				}
			}, response, request).detach();
		}

		void similar_by_permlink(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
			std::thread([](std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
				nlohmann::json reqBody, resBody;

				try {
					// Parse request Body			
					Helper::parseBody(request, reqBody);
					if (!reqBody.count("permlink"))
						throw std::runtime_error("permlink not found");
					if (!reqBody.count("author"))
						throw std::runtime_error("author not found");
					if (!reqBody.count("amount"))
						throw std::runtime_error("amount not found");
					const size_t amount = reqBody["amount"].get<size_t>();

					// Get that post
					bsoncxx::stdx::optional<bsoncxx::document::value> maybe_doc;
					{
						auto client = GLOBAL::MongoDB::mongoPool.acquire();
						auto post_info = (*client)["hive-discover"]["post_info"];
						auto post_data = (*client)["hive-discover"]["post_data"];

						// Get post._id
						maybe_doc = post_info.find_one(
							{ bsoncxx::builder::basic::make_document(
								bsoncxx::builder::basic::kvp("author", reqBody["author"].get<std::string>()),
								bsoncxx::builder::basic::kvp("permlink", reqBody["permlink"].get<std::string>())
						) });
						if (!maybe_doc)
							throw std::runtime_error("Post in post_info not found"); // Cannot find that post


						// get post.categories
						maybe_doc = post_data.find_one({
							bsoncxx::builder::basic::make_document(
								bsoncxx::builder::basic::kvp("_id", maybe_doc->view()["_id"].get_int32().value)
						) });
						if (!maybe_doc)
							throw std::runtime_error("Post in post_data not found"); // Cannot find that post				

					}
					bsoncxx::v_noabi::document::view post_document = maybe_doc->view();

					// Parse Category-Vector
					std::vector<float> categories(46);
					{
						const bsoncxx::document::element elemCategory = post_document["categories"];
						if (elemCategory.type() != bsoncxx::type::k_array)
							throw std::runtime_error("Post not analyzed");

						const bsoncxx::array::view post_category{ elemCategory.get_array().value };
						auto d_it = categories.begin();
						for (auto c_it = post_category.begin(); c_it != post_category.end(), d_it != categories.end(); ++d_it, ++c_it)
							*d_it = c_it->get_double().value;
					}

					// Search similars
					std::vector<std::vector<int>> results;
					getSimilarPostsByCategory({ categories }, amount, results);

					// Return Ids
					resBody["status"] = "ok";
					resBody["posts"] = {};
					if (results.size()) {
						// We got a result
						for (size_t i = 0; i < results[0].size(); ++i)
							resBody["posts"][std::to_string(i)] = results[0][i];
					}
					

					Helper::writeJSON(response, resBody);
				}
				catch (std::exception ex) {
					std::cout << "[ERROR] Exception raised at similar-by-permlink: " << ex.what() << std::endl;
					resBody["status"] = "failed";
					resBody["error"] = ex.what();
					Helper::writeJSON(response, resBody, "500");
				}
				}, response, request).detach();
		}
		
	}

	namespace Listener {


		void defineRoutes() {
			using namespace Endpoints;

			server.resource["^/$"]["GET"] = index;
			server.resource["^/feed$"]["POST"] = feed;
			server.resource["^/similar-category"]["POST"] = similar_by_category;
			server.resource["^/similar-permlink"]["POST"] = similar_by_permlink;
		}

		void startAPI() {
			// Configure Server
			server.config.port = GLOBAL::NswAPI_Port;
			server.config.address = GLOBAL::Host;
			server.config.thread_pool_size = 5;

			defineRoutes();

			// Start it
			serverThread = std::thread([]() {server.start(); });
		}
	}
}