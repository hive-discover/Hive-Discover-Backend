#include "NswAPI/listener.h"

#include <boost/algorithm/string.hpp>
#include <bsoncxx/builder/basic/document.hpp>
#include <bsoncxx/builder/basic/array.hpp>
#include <bsoncxx/builder/basic/kvp.hpp>
#include <bsoncxx/json.hpp>
#include "main.h"
#include <mongocxx/client.hpp>
#include <nlohmann/json.hpp>
#include "NswAPI/index.h"
#include <set>
#include "Others/strings.h"

using bsoncxx::builder::basic::kvp;
using bsoncxx::builder::basic::make_document;
using bsoncxx::builder::basic::make_array;

namespace NswAPI {

	std::vector<std::string> tokenizer(const std::string& p_pcstStr, char delim) {
		std::vector<std::string> tokens;
		std::stringstream mySstream(p_pcstStr);
		std::string temp;

		while (getline(mySstream, temp, delim))
			tokens.push_back(temp);

		return tokens;
	}

	namespace Endpoints {
		void index(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
			// Server Ready and not shutting down?
			if (Helper::serverIsReady(response, request) == false)	return;

			nlohmann::json resBody;
			resBody["status"] = "ok";
			Helper::writeJSON(response, resBody);
		}

		void feed(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
			// Server Ready and not shutting down?
			if (Helper::serverIsReady(response, request) == false)	return;

			std::thread([](std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
				nlohmann::json reqBody, resBody;

				try {
					// Parse request Body			
					Helper::parseBody(request, reqBody);

					// Set variables
					int account_id, amount = 50, abstraction_value = 2;
					std::string index_name = Categories::DEFAULT_INDEX_NAME;
					{
						if (!reqBody.count("account_id"))
							throw std::runtime_error("account_id not found");
						account_id = reqBody["account_id"].get<int>();
						if (reqBody.count("amount"))
							amount = std::min(250, reqBody["amount"].get<int>());
						if (reqBody.count("abstraction_value"))
							abstraction_value = std::min(100, reqBody["abstraction_value"].get<int>());
						if (reqBody.count("index_name") && Categories::ALL_INDEXES.count(reqBody["index_name"].get<std::string>()))
							index_name = reqBody["index_name"].get<std::string>();
					}

					// Get feed
					std::vector<int> post_results;
					NswAPI::makeFeed(account_id, abstraction_value, amount, index_name, post_results);

					// Enter feed
					resBody["status"] = "ok";
					resBody["index_name"] = index_name;
					resBody["posts"] = post_results;

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

		void similar_by_permlink(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
			// Server Ready and not shutting down?
			if (Helper::serverIsReady(response, request) == false)	return;

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

					// Get index_name
					std::string index_name = Categories::DEFAULT_INDEX_NAME;
					if (reqBody.count("index_name") && Categories::ALL_INDEXES.count(reqBody["index_name"].get<std::string>()))
						index_name = reqBody["index_name"].get<std::string>();

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

					// Parse Document-Vectors and find similar ids
					const int post_id = post_document["_id"].get_int32().value;
					const bsoncxx::document::view doc_vectors = post_document["doc_vectors"].get_document().value;
					std::map<std::string, std::vector<int>> similar_result; // lang, similar posts		
					for (const auto& pair : doc_vectors) {
						// Binary to vector
						std::vector<float> current_vector = {};
						{
							// Set size and enter all elements
							const uint8_t* first = pair.get_binary().bytes;
							const uint32_t b_size = pair.get_binary().size;
							current_vector.resize(b_size / sizeof(float));

							for (size_t i = 0; i < b_size / sizeof(float); ++i)
								current_vector[i] = *(reinterpret_cast<const float*>(first + i * sizeof(float)));
						}
						std::string current_lang = pair.key().to_string();

						// Find similar and enter them. Amount + 1 because maybe the query-doc is inside results and we interpret amount as minimun
						std::vector<std::vector<int>> results;
						NswAPI::Categories::getSimilarPostsByDocVector(index_name, current_lang, { current_vector }, amount + 1, results);
						if (!results.size())
							continue;

						// Remove query-post-id
						for (auto it = results[0].begin(); it != results[0].end(); ++it) {
							if (*it == post_id) {
								results[0].erase(it);
								break;
							}
						}
						similar_result[current_lang] = results[0];
					}


					// Build response
					resBody["status"] = "ok";
					resBody["index_name"] = index_name;
					resBody["posts"] = {};
					for (const auto& lang_results : similar_result)
						resBody["posts"][lang_results.first] = lang_results.second;

					Helper::writeJSON(response, resBody);
				}
				catch (std::exception ex) {
					std::cout << "[ERROR] Exception raised at similar-by-permlink: " << ex.what() << std::endl;
					resBody["status"] = "failed";
					resBody["error"] = ex.what();
					Helper::writeJSON(response, resBody, "500");
				}
				},
				response, request).detach();
		}

		void similar_from_author(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
			// Server Ready and not shutting down?
			if (Helper::serverIsReady(response, request) == false)	return;
			
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

					// (optional) tag in request-body
					const size_t amount = reqBody["amount"].get<size_t>();
					const std::string s_author = reqBody["author"].get<std::string>();

					auto client = GLOBAL::MongoDB::mongoPool.acquire();
					auto post_info = (*client)["hive-discover"]["post_info"];

					// Get all posts from him (Aggregation Pipeline)
					std::map<std::string, std::map<std::string, std::vector<float>>> lang_search_vectors = {}; // lang, permlink, doc-vector
					std::map<std::string, std::vector<float>> source_vector = {}; // lang, doc-vectors
					{
						using namespace bsoncxx::builder::basic;

						mongocxx::pipeline p{};
						p.match(make_document(kvp("author", s_author)));
						// Get & Unwind post-data and filter out which have no doc-vectors
						p.lookup(
							make_document(
								kvp("from", "post_data"),
								kvp("localField", "_id"),
								kvp("foreignField", "_id"),
								kvp("as", "data")
							)
						);
						p.unwind(
							make_document(
								kvp("path", "$data"),
								kvp("preserveNullAndEmptyArrays", false)
							)
						);
						p.match(
							make_document(
								kvp("data.doc_vectors", make_document(kvp("$exists", true))),
								kvp("data.doc_vectors", make_document(kvp("$ne", make_document()))),
								kvp("data.doc_vectors", make_document(kvp("$ne", NULL)))
							)
						);

						// Get & Unwind post-raw and change projection
						p.lookup(
							make_document(
								kvp("from", "post_raw"),
								kvp("localField", "_id"),
								kvp("foreignField", "_id"),
								kvp("as", "raw")
							)
						);
						p.unwind(
							make_document(
								kvp("path", "$raw"),
								kvp("preserveNullAndEmptyArrays", false)
							)
						);
						p.project(
							make_document(
								kvp("permlink", 1),
								kvp("doc_vectors", "$data.doc_vectors"),
								kvp("tags", make_document(
									kvp("$concatArrays",
										make_array(
											make_document(
												kvp("$split", make_array("$raw.raw.json_metadata.tags", " "))
											),
											make_array("$raw.raw.category")
										)
									)
								))
							)
						);

						// Filter (maybe) for tag
						if (reqBody.count("tag") && reqBody["tag"].is_string()) {
							p.match(make_document(
								kvp("tags", reqBody["tag"].get<std::string>())
							));
						}

						// Retrieve everything, decode doc-vectors and enter in list
						auto cursor = post_info.aggregate(p, mongocxx::options::aggregate{});
						std::vector<float> vector;
						for (const auto& doc : cursor) {
							// Parse Permlink 
							const std::string permlink = doc["permlink"].get_utf8().value.to_string().c_str();

							// Parse all doc-vectors for each lang
							for (const auto& pair : doc["doc_vectors"].get_document().view()) {
								// Parse Item
								std::string current_lang = pair.key().to_string();
								{
									// Set size and enter all elements
									const uint8_t* first = pair.get_binary().bytes;
									const uint32_t b_size = pair.get_binary().size;
									vector.resize(b_size / sizeof(float));

									for (size_t i = 0; i < b_size / sizeof(float); ++i)
										vector[i] = *(reinterpret_cast<const float*>(first + i * sizeof(float)));
								}

								// Is this post the query-source?
								if (permlink == reqBody["permlink"].get<std::string>()) {
									source_vector[current_lang] = vector;
									continue;
								}

								// No ==> Enter in search-vectors
								if (!lang_search_vectors.count(current_lang))
									lang_search_vectors[current_lang] = {};
								lang_search_vectors[current_lang][permlink] = vector;
							}
						}
					}

					// Found Post?
					if (source_vector.size() == 0) {
						// no
						resBody["status"] = "failed";
						resBody["error"] = "Post does not exist";
						Helper::writeJSON(response, resBody);
						return;
					}

					// Search for most-similar content (Cosine-Simalarity)
					std::vector<std::pair<std::string, float>> search_vec_scores; // permlink, cosine-similarity score
					for (const auto& lang_posts_pair : lang_search_vectors) {
						const std::string& lang = lang_posts_pair.first;
						const std::map<std::string, std::vector<float>>& posts = lang_posts_pair.second;

						if (!source_vector.count(lang))
							continue; // Skip this lang: source post does not contain this lang

						// Go though all post's doc-vectors
						for (const auto& permlink_vector_pair : posts) {
							const std::string& permlink = permlink_vector_pair.first;
							const std::vector<float>& doc_vector = permlink_vector_pair.second;

							// Calc cosine-simalarity
							float dot = 0.0, denom_a = 0.0, denom_b = 0.0;
							for (unsigned int i = 0u; i < source_vector[lang].size(); ++i) {
								dot += source_vector[lang][i] * doc_vector[i];
								denom_a += source_vector[lang][i] * source_vector[lang][i];
								denom_b += doc_vector[i] * doc_vector[i];
							}

							// Enter in search_vec_scores
							const float cosine_sim_score = dot / (sqrt(denom_a) * sqrt(denom_b));
							search_vec_scores.push_back(std::pair<std::string, float>(permlink, cosine_sim_score));
						}
					}

					// Sort search_vec_scores 
					std::sort(
						search_vec_scores.begin(),
						search_vec_scores.end(),
						// Define Sort-Method
						[](const std::pair<std::string, float>& a, const std::pair<std::string, float>& b) {
							return (a.second > b.second); // (lowest score == worst item)
						}
					);

					// Build response
					resBody["status"] = "ok";
					resBody["posts"] = std::vector<nlohmann::json>();
					if (reqBody.count("tag") && reqBody["tag"].is_string())
						resBody["tag"] = reqBody["tag"].get<std::string>();

					// Add best permlinks to the response
					{
						std::set<std::string> best_permlinks;
						for (unsigned int i = 0; i < search_vec_scores.size() && best_permlinks.size() < amount; ++i) {
							const auto& pair = search_vec_scores[i];
							if (best_permlinks.count(pair.first))
								continue; // Already a better version inside

							// Add Item to response
							resBody["posts"].push_back({ {"author", s_author}, {"permlink", pair.first}, {"sim", pair.second} });
							best_permlinks.insert(pair.first);
						}
					}


					Helper::writeJSON(response, resBody);
				}
				catch (std::exception ex) {
					std::cout << "[ERROR] Exception raised at similar-from-author: " << ex.what() << std::endl;
					resBody["status"] = "failed";
					resBody["error"] = ex.what();
					Helper::writeJSON(response, resBody, "500");
				}
				},
				response, request).detach();
		}

		void similar_in_category(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
			// Server Ready and not shutting down?
			if (Helper::serverIsReady(response, request) == false)	return;
			
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
					const std::string s_author = reqBody["author"].get<std::string>();
					const std::string s_permlink = reqBody["permlink"].get<std::string>();

					auto client = GLOBAL::MongoDB::mongoPool.acquire();
					auto post_info = (*client)["hive-discover"]["post_info"];
					auto post_raw = (*client)["hive-discover"]["post_raw"];
					auto post_data = (*client)["hive-discover"]["post_data"];

					// Get the source-post and community-tag
					bsoncxx::document::view source_post;
					std::string community_tag = "";
					std::map<std::string, std::vector<float>> source_vectors; // lang, vector
					{
						bsoncxx::stdx::optional<bsoncxx::document::value> maybe_post = post_info.find_one(make_document(kvp("author", s_author), kvp("permlink", s_permlink)));
						if (!maybe_post) {
							// no
							resBody["status"] = "failed";
							resBody["error"] = "Post does not exist";
							Helper::writeJSON(response, resBody);
							return;
						}

						// Found ==> Set Post and Get community-tag
						source_post = maybe_post->view();
						community_tag = source_post["parent_permlink"].get_utf8().value.to_string();
						const int post_id = source_post["_id"].get_int32().value;

						// Get doc-vectors
						maybe_post = post_data.find_one(make_document(kvp("_id", post_id)));
						if (!maybe_post)
							throw std::runtime_error("Cannot Find Post in post_data");

						// Parse Binary Data
						for (const auto& elem : maybe_post->view()["doc_vectors"].get_document().value) {
							const std::string current_lang = elem.key().to_string();
							source_vectors[current_lang] = {};

							// Set size and enter all elements
							const uint8_t* first = elem.get_value().get_binary().bytes;
							const uint32_t b_size = elem.get_value().get_binary().size;
							source_vectors[current_lang].resize(b_size / sizeof(float));

							for (size_t i = 0; i < b_size / sizeof(float); ++i)
								source_vectors[current_lang][i] = *(reinterpret_cast<const float*>(first + i * sizeof(float)));
						}
					}

					// Post not found
					if (!source_vectors.size()) {
						// no
						resBody["status"] = "failed";
						resBody["error"] = "Post does not exist";
						Helper::writeJSON(response, resBody);
						return;
					}


					// Create Agg-Pipeline to retrieve all posts of this community by the last 7 days
					mongocxx::pipeline agg_pl{};
					{
						bsoncxx::types::b_date minDate = bsoncxx::types::b_date(std::chrono::system_clock::now() - std::chrono::hours{ 7 * 24 });
						agg_pl.match(make_document(
							kvp("parent_permlink", community_tag),
							kvp("timestamp", make_document(kvp("$gt", minDate)))
						));
						// Get & Unwind post-data and filter out which have no doc-vectors
						agg_pl.lookup(
							make_document(
								kvp("from", "post_data"),
								kvp("localField", "_id"),
								kvp("foreignField", "_id"),
								kvp("as", "data")
							)
						);
						agg_pl.unwind(
							make_document(
								kvp("path", "$data"),
								kvp("preserveNullAndEmptyArrays", false)
							)
						);
						agg_pl.match(
							make_document(
								kvp("data.doc_vectors", make_document(kvp("$exists", true))),
								kvp("data.doc_vectors", make_document(kvp("$ne", make_document()))),
								kvp("data.doc_vectors", make_document(kvp("$ne", NULL)))
							)
						);

						// Change Projection
						agg_pl.project(
							make_document(
								kvp("permlink", 1),
								kvp("author", 1),
								kvp("doc_vectors", "$data.doc_vectors")
							)
						);
					}

					// Process all comunity-posts and calc simalarity-scores
					using cosine_result_t = std::tuple<std::string, std::string, float>; // author, permlink, cosine-similarity score
					std::vector<cosine_result_t> search_vec_scores; 
					auto cursor = post_info.aggregate(agg_pl, mongocxx::options::aggregate{});
					std::vector<float> v_vector;
					for (const auto& doc : cursor) {
						const std::string current_permlink = doc["permlink"].get_utf8().value.to_string();
						const std::string current_author = doc["author"].get_utf8().value.to_string();
						if (current_permlink == s_permlink && current_author == s_author)
							continue; // Is source post ==> skip

						// Go through all post-langs
						for (const auto& elem : doc["doc_vectors"].get_document().value) {
							const std::string current_lang = elem.key().to_string();

							// Parse Binary Doc-Vectors to std::vector<float>
							{
								const uint8_t* first = elem.get_value().get_binary().bytes;
								const uint32_t b_size = elem.get_value().get_binary().size;
								v_vector.resize(b_size / sizeof(float));

								for (size_t i = 0; i < b_size / sizeof(float); ++i)
									v_vector[i] = *(reinterpret_cast<const float*>(first + i * sizeof(float)));
							}

							// Calc cosine-simalarity
							float dot = 0.0, denom_a = 0.0, denom_b = 0.0;
							for (unsigned int i = 0u; i < source_vectors[current_lang].size(); ++i) {
								dot += source_vectors[current_lang][i] * v_vector[i];
								denom_a += source_vectors[current_lang][i] * source_vectors[current_lang][i];
								denom_b += v_vector[i] * v_vector[i];
							}

							// Enter in search_vec_scores
							const float cosine_sim_score = dot / (sqrt(denom_a) * sqrt(denom_b));
							search_vec_scores.push_back(std::make_tuple(current_author, current_permlink, cosine_sim_score));
						}
					}


					// Sort search_vec_scores 
					std::sort(
						search_vec_scores.begin(),
						search_vec_scores.end(),
						// Define Sort-Method
						[](const cosine_result_t& a, const cosine_result_t& b) {
							return (std::get<2>(a) > std::get<2>(b)); // (lowest score == worst item)
						}
					);

					// Build response
					resBody["status"] = "ok";
					resBody["posts"] = std::vector<nlohmann::json>();
					if (reqBody.count("tag") && reqBody["tag"].is_string())
						resBody["tag"] = reqBody["tag"].get<std::string>();

					// Add best permlinks to the response
					{
						std::set<std::string> best_authorperms;
						for (unsigned int i = 0; i < search_vec_scores.size() && best_authorperms.size() < amount; ++i) {
							// Get pair-data
							const cosine_result_t& pair = search_vec_scores[i];
							const std::string author = std::get<0>(pair);
							const std::string permlink = std::get<1>(pair);
							const float sim_score = std::get<2>(pair);
							const std::string authorperm = "@" + author + "/" + permlink;

							if (best_authorperms.count(authorperm))
								continue; // Already a better version inside

							// Add Item to response
							resBody["posts"].push_back({ {"author", author}, {"permlink", permlink}, {"sim", sim_score} });
							best_authorperms.insert(authorperm);
						}
					}


					Helper::writeJSON(response, resBody);
				}
				catch (std::exception ex) {
					std::cout << "[ERROR] Exception raised at similar-in-category: " << ex.what() << std::endl;
					resBody["status"] = "failed";
					resBody["error"] = ex.what();
					Helper::writeJSON(response, resBody, "500");
				}
				},
				response, request).detach();
		}

		void similar_accounts(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
			// Server Ready and not shutting down?
			if (Helper::serverIsReady(response, request) == false)	return;
			
			std::thread([](std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
				nlohmann::json reqBody, resBody;

				try {
					// Parse request Body			
					Helper::parseBody(request, reqBody);
					if (!reqBody.count("account_name") && !reqBody.count("account_id"))
						throw std::runtime_error("no account_name and no account_id found");
					if (!reqBody.count("amount"))
						throw std::runtime_error("amount not found");
					const size_t amount = reqBody["amount"].get<size_t>();

					auto client = GLOBAL::MongoDB::mongoPool.acquire();
					auto account_info = (*client)["hive-discover"]["account_info"];

					// Find that account_interests
					bsoncxx::document::view_or_value find_query;
					if (reqBody.count("account_name")) {
						// Use name
						find_query = bsoncxx::builder::basic::make_document(
							bsoncxx::builder::basic::kvp("name", reqBody["account_name"].get<std::string>())
						);
					}
					else {
						// Use _id
						find_query = bsoncxx::builder::basic::make_document(
							bsoncxx::builder::basic::kvp("_id", reqBody["account_id"].get<std::string>())
						);
					}

					bsoncxx::stdx::optional<bsoncxx::document::value> maybe_doc = account_info.find_one(find_query);
					if (!maybe_doc)
						throw std::runtime_error("Account cannot be found");
					bsoncxx::v_noabi::document::view account_document = maybe_doc->view();
					const int account_id = account_document["_id"].get_int32().value;

					// Parse all Interests-Vector
					std::map<std::string, std::vector<float>> lang_interests;
					if(account_document["interests"]) {
						std::vector<float> current_vector = {};
						const bsoncxx::document::view doc_vectors = account_document["interests"].get_document().value;			
						for (const auto& pair : doc_vectors) {
							// Convert Binary to Vector and then push it to the map
							{
								// Set size and enter all elements
								const uint8_t* first = pair.get_binary().bytes;
								const uint32_t b_size = pair.get_binary().size;
								current_vector.resize(b_size / sizeof(float));

								for (size_t i = 0; i < b_size / sizeof(float); ++i)
									current_vector[i] = *(reinterpret_cast<const float*>(first + i * sizeof(float)));
							}

							std::string current_lang = pair.key().to_string();
							lang_interests[current_lang] = current_vector;
						}
					}

					// Nothing available?
					if (lang_interests.size() == 0) {
						resBody["status"] = "ok";
						resBody["info"] = "This account is not active";
						resBody["accounts"] = std::vector<float>(0);
						Helper::writeJSON(response, resBody);
						return;
					}

					// Search similar accounts and rank based on their distance (lowest is the best)
					std::map<std::string, knn_result_t> results;
					std::multimap<float, int> acc_distances; // distance, acc-id
					Accounts::getSimilarAccounts(lang_interests, amount + 1, results);
					for (auto& lang_res_item : results) {
						// Pop all items to the multimap
						knn_result_t r_queue = lang_res_item.second;
						while (!r_queue.empty()) {
							acc_distances.insert(r_queue.top());
							r_queue.pop();					
						}
					}


					// Get nearest account-ids without his own id
					std::set<int> similar_accounts;
					for (auto it = acc_distances.lower_bound(0); it != acc_distances.end(), similar_accounts.size() < amount; ++it) {
						if(account_id != it->second)
							similar_accounts.insert(it->second);
					}

					// Return Ids
					resBody["status"] = "ok";
					resBody["accounts"] = similar_accounts;
					Helper::writeJSON(response, resBody);
				}
				catch (std::exception ex) {
					std::cout << "[ERROR] Exception raised at similar-accounts: " << ex.what() << std::endl;
					resBody["status"] = "failed";
					resBody["error"] = ex.what();
					Helper::writeJSON(response, resBody, "500");
				}
				}, response, request).detach();
		}

		void text_searching(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
			// Server Ready and not shutting down?
			if (Helper::serverIsReady(response, request) == false)	return;

			std::thread([](std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request) {
				nlohmann::json reqBody, resBody;

				try {
					// Parse request Body			
					Helper::parseBody(request, reqBody);
					if (!reqBody.count("query"))
						throw std::runtime_error("query not found");
					if (!reqBody.count("amount"))
						reqBody["amount"] = 100;
					if (!reqBody.count("index_name"))
						reqBody["index_name"] = Categories::DEFAULT_INDEX_NAME;
					if (!reqBody.count("lang"))
						reqBody["lang"] = "*";

					const std::string query = boost::algorithm::to_lower_copy(reqBody["query"].get<std::string>());		
					const std::string lang = reqBody["lang"].get<std::string>();
					const std::string index_name = reqBody["index_name"].get<std::string>();
					const size_t amount = reqBody["amount"].get<size_t>();
					
					// Split query in tokens
					const std::vector<std::string> query_tokens = tokenizer(query, ' ');
					const int query_token_len = query_tokens.size();
					bsoncxx::builder::basic::array barr_tokens = {};
					for (const auto& tok : query_tokens)
						barr_tokens.append(tok);
	
					// Establish Connection
					auto client = GLOBAL::MongoDB::mongoPool.acquire();
					auto col_post_data = (*client)["hive-discover"]["post_data"];
					auto db_fasttext = (*client)["fasttext"];
					std::vector<std::string> fasttext_langs = db_fasttext.list_collection_names();
					const auto token_find_query = make_document(kvp("_id", make_document(kvp("$in", barr_tokens))));
					
					if (lang != "*") // Only one lang is wished
						fasttext_langs = { lang };

					// Vectorize query in all langs
					std::map<std::string, std::vector<float>> lang_vquery; // vectorized query for each lang
					std::map<std::string, int> lang_tcounter; // known-token-count for each lang		
					for (const std::string lang : fasttext_langs) {
						// Find all words for this lang
						auto cursor = db_fasttext[lang].find(make_document(kvp("_id", make_document(kvp("$in", barr_tokens)))));
						for (const auto& tok_doc : cursor) {
							// Convert Binary to Vector
							const auto bin_data = tok_doc["v"].get_binary();
							std::vector<float> current_vector = {};
							{
								// Set size and enter all elements
								const uint8_t* first = bin_data.bytes;
								const uint32_t b_size = bin_data.size;
								current_vector.resize(b_size / sizeof(float));

								for (size_t i = 0; i < b_size / sizeof(float); ++i)
									current_vector[i] = *(reinterpret_cast<const float*>(first + i * sizeof(float)));
							}

							float idf = 0;
							if (tok_doc["idf"].type() == bsoncxx::type::k_int32)
								idf = static_cast<float>(tok_doc["idf"].get_int32().value);
							else if (tok_doc["idf"].type() == bsoncxx::type::k_double)
								idf = tok_doc["idf"].get_double().value;

							if (!lang_vquery.count(lang)) {
								// First item of this lang
								lang_vquery[lang] = std::vector<float>(300);
								lang_tcounter[lang] = 0;
							}				

							// Add this token to vquery and countings with tf and idf values. tf is (assuming every word is only 
							// 1 time in the query) 1/token_len and idf comes from the DB
							lang_tcounter[lang] += 1;
							auto tok_it = current_vector.begin();
							for (auto vq_it = lang_vquery[lang].begin(); vq_it != lang_vquery[lang].end(), tok_it != current_vector.end(); ++vq_it, ++tok_it)
								*vq_it += *tok_it * idf * (1.0f / query_token_len);
						}
					}
					
					// Remove low countings (<50% of known-tokens)
					{
						std::vector<std::string> remove_langs;
						for (const auto& l_counting : lang_tcounter) {
							if (l_counting.second / query_token_len < 0.5)
								remove_langs.push_back(l_counting.first);
						}

						for (const auto& lang : remove_langs) {
							lang_vquery.erase(lang);
							lang_tcounter.erase(lang);
						}
					}

					// Nothing to do?
					if (lang_vquery.size() == 0) {
						resBody["status"] = "ok";
						resBody["index_name"] = index_name;
						resBody["results"] = std::vector<float>(0);

						Helper::writeJSON(response, resBody);
						return;
					}

					// Searching similar to query-vector
					std::multimap<float, int> post_distances; // distance, acc-id
					for (const auto& search_item : lang_vquery) {
						// Search and push to result-map
						std::vector<knn_result_t> res;
						Categories::getSimilarPostsByDocVector(index_name, search_item.first, { search_item.second }, amount, res);
						if (!res.size())
							continue; // Nothing found

						// Enter results into multimap
						while (!res[0].empty()) {
							post_distances.insert(res[0].top());
							res[0].pop();
						}
					}
					
					// Set nearest posts in this (unique values in a sorted way)
					std::vector<int> nearest_posts;
					for (auto d_it = post_distances.lower_bound(0); d_it != post_distances.end(), nearest_posts.size() < amount; ++d_it) {
						const int _id = d_it->second;
						std::vector<int>::iterator _id_iterator = nearest_posts.end();

						for (auto p_it = nearest_posts.begin(); p_it != nearest_posts.end(); ++p_it) {
							if (*p_it == _id) {
								// Found it already in
								_id_iterator = p_it;
								break;
							}
						}

						if (_id_iterator == nearest_posts.end())
							nearest_posts.push_back(_id); // Found it not inside					
					}

					// Build response
					resBody["status"] = "ok";
					resBody["index_name"] = index_name;
					resBody["results"] = nearest_posts;

					Helper::writeJSON(response, resBody);
				}
				catch (std::exception ex) {
					std::cout << "[ERROR] Exception raised at similar-by-permlink: " << ex.what() << std::endl;
					resBody["status"] = "failed";
					resBody["error"] = ex.what();
					Helper::writeJSON(response, resBody, "500");
				}
				},
				response, request).detach();
		}
	}

	namespace Listener {


		void defineRoutes() {
			using namespace Endpoints;

			server.resource["^/$"]["GET"] = index;
			server.resource["^/feed$"]["POST"] = feed;

			server.resource["^/similar-permlink"]["POST"] = similar_by_permlink;
			server.resource["^/similar-accounts"]["POST"] = similar_accounts;
			server.resource["^/similar-from-author"]["POST"] = similar_from_author;
			server.resource["^/similar-in-category"]["POST"] = similar_in_category;

			server.resource["^/text-searching"]["POST"] = text_searching;
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