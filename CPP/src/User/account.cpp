#include "User/account.h"

#include <boost/utility/string_view.hpp>
#include <boost/utility/string_view_fwd.hpp>
#include <bsoncxx/json.hpp>
#include <bsoncxx/builder/basic/document.hpp>
#include <bsoncxx/builder/basic/kvp.hpp>
#include "main.h"
#include <mongocxx/client.hpp>
#include <thread>
#include <vector>

using bsoncxx::type;
using bsoncxx::builder::basic::kvp;
using bsoncxx::builder::basic::make_document;
using bsoncxx::builder::basic::make_array;

namespace User {
	namespace Account {

		void getActivities(
			const int account_id,
			std::vector<int>& post_ids,
			std::vector<int>& votes_ids
		) {
			std::thread post_getter([account_id, &post_ids]() {
				// Get a connection
				mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
				auto post_info = (*client)["hive-discover"]["post_info"];
				auto account_info = (*client)["hive-discover"]["account_info"];

				// Find account_name
				bsoncxx::stdx::optional<bsoncxx::document::value> maybe_doc = account_info.find_one(
					{ make_document(kvp("_id", account_id)) }
				);
				if (!maybe_doc)
					return; // Cannot find account

				const auto account_document = maybe_doc->view();
				auto account_name = account_document["name"].get_utf8().value;


				// Get all posts written by him
				bsoncxx::v_noabi::document::view_or_value findQuery = { make_document(kvp("author", account_name)) };
				auto cursor = post_info.find(findQuery);

				// Retrieve Ids, where categories is not null
				bsoncxx::document::element elemId;
				for (const auto& post_item : cursor) {
					if (post_item["categories"].type() == type::k_array)
						post_ids.push_back(post_item["_id"].get_int32().value);
				}

				});
				
			std::thread vote_getter([account_id, &votes_ids]() {
				// Prepare connection
				mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
				auto post_data = (*client)["hive-discover"]["post_data"];
				bsoncxx::v_noabi::document::view_or_value findQuery = make_document(kvp("votes", account_id));

				// Get all votes
				auto cursor = post_data.find(findQuery);

				// Retrieve Ids, where categories is not null
				bsoncxx::document::element elemId;
				for (const auto& post_item : cursor) {
					if (post_item["categories"].type() == type::k_array)
						votes_ids.push_back(post_item["_id"].get_int32().value);
				}

				});
		
			// wait for both to complete
			if (post_getter.joinable())
				post_getter.join();
			if (vote_getter.joinable())
				vote_getter.join();
		}

		void getActivitiesCount(
			const int account_id, 
			int& post_count, 
			int& vote_count
		) {
			std::thread post_getter([account_id, &post_count]() {
				// Get a connection
				mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
				auto post_info = (*client)["hive-discover"]["post_info"];
				auto account_info = (*client)["hive-discover"]["account_info"];

				// Find account_name
				bsoncxx::stdx::optional<bsoncxx::document::value> maybe_doc = account_info.find_one(
					{ make_document(kvp("_id", account_id)) }
				);
				if (!maybe_doc)
					return; // Cannot find account

				//const auto account_document = maybe_doc->view();
				//auto account_name = account_document["name"].get_utf8().value;

				// Get count of all posts written by him
				bsoncxx::v_noabi::document::view_or_value findQuery = { 
					make_document(
						kvp("author", maybe_doc->view()["name"].get_utf8().value)
					) 
				};
				post_count = post_info.count_documents(findQuery);
			});

			std::thread vote_getter([account_id, &vote_count]() {
				// Prepare connection
				mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
				auto post_data = (*client)["hive-discover"]["post_data"];
				bsoncxx::v_noabi::document::view_or_value findQuery = make_document(kvp("votes", account_id));

				// Get count of all votes
				vote_count = post_data.count_documents(findQuery);		
			});

			// wait for both to complete
			if (post_getter.joinable())
				post_getter.join();
			if (vote_getter.joinable())
				vote_getter.join();
		}

		void getLangs(
			const int account_id, 
			bsoncxx::builder::basic::array& accLangs, 
			std::vector<int>& post_ids, 
			std::vector<int>& votes_ids
		) {
			if (!post_ids.size() && !votes_ids.size()) // Nothing available ==> Get Activities
				getActivities(account_id, post_ids, votes_ids);

			// Convert Ids to list
			bsoncxx::builder::basic::array barrPostIds{};
			for (const auto id : post_ids)
				barrPostIds.append(id);
			for (const auto id : votes_ids)
				barrPostIds.append(id);

			mongocxx::v_noabi::pool::entry client = GLOBAL::MongoDB::mongoPool.acquire();
			auto post_data = (*client)["hive-discover"]["post_data"];
			auto cursor = post_data.find(make_document(kvp("_id", make_document(kvp("$in", barrPostIds)))));

			// Enter all Langs into Map
			std::map<std::string, float> allLangs;
			float totalScore = 0;
			for (const auto& doc : cursor) {
				const bsoncxx::document::element elemLangs = doc["lang"];
				if (elemLangs.type() != type::k_array)
					continue; // Not analyzed yet		

				// Iterate through all items and add scores
				for (const bsoncxx::array::element& langItem : elemLangs.get_array().value) {
					const bsoncxx::document::element score = langItem.get_document().value["x"];
					const bsoncxx::document::element lang = langItem.get_document().value["lang"];

					if (score.type() != type::k_double || lang.type() != type::k_utf8)
						continue; // Not ready

					allLangs[lang.get_utf8().value.to_string()] += score.get_double().value;
					totalScore += score.get_double().value;
				}
			}

			// Calc percentages and enter all over 15%
			for (const auto& item : allLangs) {
				if ((item.second / totalScore) > 0.15)
					accLangs.append(item.first);
			}
		}
	}
}