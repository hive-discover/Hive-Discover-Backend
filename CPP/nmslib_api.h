#ifndef NMSLIB_API_H
#define NMSLIB_API_H

#include "Simple-Web-Server/server_http.hpp"
using HttpServer = SimpleWeb::Server<SimpleWeb::HTTP>;

/// <summary>
/// Entrypoint for top main.cpp to start the NMSLIB-API
/// </summary>
/// <param name="port">Which Http-Port should the API run?</param>
/// <returns>Status Code (when API exits). Mainly an error code!</returns>
int runAPI(const int port);

namespace Endpoints {
    /// <summary>
    /// Handle Path: "/" GET
    /// ==> Check if Server is running
    /// </summary>
    /// <param name="response"></param>
    /// <param name="request"></param>
    void index(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request);

    /// <summary>
    /// Handle Path: "/feed" POST
    /// ==> Create a Feed for an Account. More information into worker.cpp->getFeed()
    /// </summary>
    /// <param name="response">Should contain: account_id, account_name, amount, abstraction_value</param>
    /// <param name="request"></param>
    void feed(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request);

    /// <summary>
    /// Handle Path: "/sort/personalized" POST
    /// </summary>
    /// <param name="response">Should contain: account_id, account_name, query_ids</param>
    /// <param name="request"></param>
    void sortPersonalized(std::shared_ptr<HttpServer::Response> response, std::shared_ptr<HttpServer::Request> request);

    /// <summary>
    /// Define all possible Entrypoints
    /// </summary>
    /// <param name="server">On which HttpServer instance should the routes be defined?</param>
    void defineRoutes(HttpServer& server);
}

#endif