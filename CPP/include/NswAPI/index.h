#ifndef NswAPI_INDEX_H
#define NswAPI_INDEX_H

#include "hnswlib/hnswlib.h"
#include <set>

namespace NswAPI {

	void makeFeed(
		const int account_id,
		const int abstraction_value,
		const int amount,
		std::unordered_set<int>& post_results
	);

	void getSimilarPostsByCategory(
		const std::vector<std::vector<float>>& query,
		const int k,
		std::vector<std::vector<int>>& result
	);

	void buildIndex();

	void start();
}

#endif