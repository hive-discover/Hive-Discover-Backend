#ifndef NswAPI_INDEX_H
#define NswAPI_INDEX_H

#include <bsoncxx/builder/basic/document.hpp>
#include "hnswlib/hnswlib.h"
#include <math.h>
#include <map>
#include <set>
#include <string>

namespace NswAPI {

	typedef std::shared_ptr<hnswlib::AlgorithmInterface<float>> index_t;
	typedef std::priority_queue<std::pair<float, hnswlib::labeltype>> knn_result_t;

	static hnswlib::L2Space space46(46);
	static hnswlib::L2Space space300(300);

	constexpr int MAX_POSTS_FOR_FEED = 250;

	template<typename T>
	void parseBinaryToVector(
		const uint8_t* first,
		const uint32_t b_size,
		std::vector<T>& result
	);

	template<typename T>
	void parseBinaryToVector(
		const bsoncxx::document::element& binary_element,
		std::vector<T>& result
	);

	template<typename T>
	uint8_t* parseVectorToBinary(
		const std::vector<T>& vector,
		uint32_t& b_size
	);

	template<typename T>
	bsoncxx::types::b_binary parseVectorToBinary(
		const std::vector<T>& vector
	);

	inline int highToLowFunc(const float x) {
		if (x < 1e-5 && x > -1e-5)
			return 0; // Undefined behaviour because it will divided by that. Overflow- or DivideByZero-Error

		return ceil(10 / x);
	}


	int start();

	namespace Categories {
		constexpr char* DEFAULT_INDEX_NAME = "general-index";
		constexpr char* DEFAULT_LANG = "en";

		// Name, Lang, index
		extern std::map<std::string, std::map<std::string, index_t>> ALL_INDEXES;

		// index buildings
		void buildOneIndexName(
			const std::string index_name, 
			const std::string id_source, 
			const std::string& query
		);
		void buildIndexes(bool in_parralel);

		// search functions
		void getSimilarPostsByDocVector(
			std::string index_name,
			std::string lang,
			const std::vector<std::vector<float>>& queries,
			const int k,
			std::vector<knn_result_t>& results
		);

		void getSimilarPostsByDocVector(
			std::string index_name,
			std::string lang,
			const std::vector<std::vector<float>>& queries,
			const int k,
			std::vector<std::vector<int>>& results
		);
	}

	namespace Accounts {

		constexpr char* DEFAULT_LANG = "en";

		std::map<std::string, std::vector<float>> calc_account_profile(const int account_id);
		void set_all_account_profiles();

		void buildIndex();

		void getSimilarAccounts(
			const std::map<std::string, std::vector<float>>& query,
			const int k,
			std::map<std::string, knn_result_t>& result
		);
	}
}

#endif