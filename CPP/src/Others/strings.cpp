#include "Others/strings.h"

#include <string>
#include <vector>

namespace Others {

	namespace Strings {

		float calcLevenshteinDistance(
			const std::string& s1,
			const std::string& s2
		) {
			// Create 2d Matrx as vector in vector
			const int rows = s1.length() + 1;
			const int colls = s2.length() + 1;
			std::vector<std::vector<int>> dis_matrix(rows, std::vector<int>(colls));

			// Fill 2d-Matrix with indexes of the character
			for (int i = 1; i < rows; ++i) {
				for (int k = 1; k < colls; ++k) {
					dis_matrix[i][0] = i;
					dis_matrix[0][k] = k;
				}
			}

			// Iterate over Matrix and compute cost (deletetions, insertions and/or substitution)
			int cost = 0, c = 0, r = 0;
			int last_dis = 0;
			for (c = 1; c < colls; ++c) {
				for (r = 1; r < rows; ++r) {
					if (s1[r - 1] == s2[c - 1])
						cost = 0;
					else
						cost = 2;

					dis_matrix[r][c] = std::min(
						std::min(
							dis_matrix[r - 1][c] + 1,		// Cost of deletions
							dis_matrix[r][c - 1] + 1		// Cost of insertions
						),		
						dis_matrix[r - 1][c - 1] + cost // Cost of substitutions
					);   
					last_dis = dis_matrix[r][c];
				}
			}

			// Calc Ratio-Distance
			return (rows + colls - 2.0f - dis_matrix[r -1][c-1]) / (rows + colls - 2.0f);
		}

	}

}
