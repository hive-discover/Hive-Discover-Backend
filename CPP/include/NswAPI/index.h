#ifndef NswAPI_INDEX_H
#define NswAPI_INDEX_H

#include "hnswlib/hnswlib.h"
#include <set>
#include <string>

namespace NswAPI {

	void makeFeed(
		const int account_id,
		const int abstraction_value,
		const int amount,
		std::unordered_set<int>& post_results
	);

	

	

	void start();

	namespace Categories {

		static const std::string INDEX_FILE_NAME = "categories_index_46.knn";

		void save();
		void load();

		void buildIndex();

		void getSimilarPostsByCategory(
			const std::vector<std::vector<float>>& query,
			const int k,
			std::vector<std::vector<int>>& result
		);
	}

	namespace Accounts {

		static const std::string INDEX_FILE_NAME = "accounts_index_46.knn";		

		void save();
		void load();

		std::vector<float> calc_account_profile(const int account_id);
		void set_all_account_profiles();

		void buildIndex();

		void getSimilarAccounts(
			const std::vector<std::vector<float>>& query,
			const int k,
			std::vector<std::vector<int>>& result
		);
	}
}

#endif