#ifndef NswAPI_CALC_FEED_H
#define NswAPI_CALC_FEED_H

#include <bsoncxx/builder/basic/document.hpp>
#include <bsoncxx/builder/basic/kvp.hpp>
#include <bsoncxx/json.hpp>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace NswAPI {

	namespace calcFeed {
		constexpr int MAX_POSTS_FOR_FEED = 100;
		
		void get_docvectors(
			const bsoncxx::builder::basic::array& post_ids,
			std::map<std::string, std::vector<std::vector<float>>>& doc_vectors
		);
		void get_docvectors(
			const bsoncxx::builder::basic::array& post_ids,
			std::map<std::string, std::vector<std::pair<int, std::vector<float>>>>& doc_vectors
		);

		void get_sample(
			const std::vector<int>& his_post_ids,
			const std::vector<int>& his_vote_ids,
			const int amount,
			std::map<std::string, std::vector<std::vector<float>>>& sample
		);

		void find_similar(
			const std::map<std::string, std::vector<std::vector<float>>>& input,
			const std::string index_name,
			const size_t k,
			std::set<int>& similar_ids,
			const std::set<int> filter_out = {} // optional to filter own activies out
		);

		void calc_sim_scores(
			const std::map<std::string, std::vector<std::pair<int, std::vector<float>>>>& similar_doc_vectors,
			const std::map<std::string, std::vector<std::vector<float>>>& sample_doc_vectors,
			std::vector<std::pair<float, int>>& sim_scores
		);

		void reorder_sim_ids_weighted(
			std::vector<std::pair<float, int>>& sim_scores
		);
	}

	void getFeed(
		const int account_id,
		const int abstraction_value,
		const int amount,
		const std::string index_name,
		std::vector<int>& post_results
	);
}

#endif