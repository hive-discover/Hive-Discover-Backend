#ifndef IMAGE_API_SEARCHING_H
#define IMAGE_API_SEARCHING_H

#include "hnswlib/hnswlib.h"
#include <memory>

namespace ImageAPI {

	typedef std::shared_ptr<hnswlib::AlgorithmInterface<float>> index_t;
	typedef std::priority_queue<std::pair<float, hnswlib::labeltype>> knn_result_t;
	
	static hnswlib::L2Space space1000(1000);
	static hnswlib::L2Space space300(300);
	static hnswlib::L2Space space50(50);

	namespace ImgSearch {
		extern index_t producton_index;

		void buildIndex();

		void search(
			const std::vector<std::vector<float>>& queries,
			const int k,
			std::vector<std::vector<int>>& results
		);

		void addSimilarImages(const int img_id);
		void calcSimilarities();
	}	

	namespace TextSearch {
		extern index_t producton_index;

		void buildIndex();	

		void search(
			const std::vector<std::vector<float>>& queries,
			const int k,
			std::vector<std::vector<int>>& results
		);
	}

	void runBuildAgent();
}

#endif