var app = angular
  .module('deciframeApp', ['ngRoute', 'ngAnimate', 'ngProgress', 'ui.bootstrap'])
  .constant('RESTAPI', {
    url: 'http://localhost:5003'
  })
  .factory('GenerosService', function($http, $q) {
    var promise = null;
    return {
      carregar: function() {
        if (!promise) {
          promise = $http.get('generos').then(function(response) {
            return response.data;
          }, function(response) {
            promise = null;
            return $q.reject(response);
          });
        }
        return promise;
      }
    };
  });
