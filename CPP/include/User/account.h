#ifndef USER_ACCOUNT_H
#define USER_ACCOUNT_H

#include <bsoncxx/builder/basic/document.hpp>
#include <bsoncxx/builder/basic/kvp.hpp>
#include <vector>


namespace User {
	namespace Account {
		void getActivities(
			const int account_id,
			std::vector<int>& post_ids,
			std::vector<int>& votes_ids
		);

		void getLangs(
			const int account_id,
			bsoncxx::builder::basic::array& accLangs,
			std::vector<int>& post_ids,
			std::vector<int>& votes_ids
		);
	}
}

#endif