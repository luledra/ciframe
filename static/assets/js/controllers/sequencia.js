angular.module('deciframeApp').controller('SequenciaController', function($http, $window, ngProgressFactory, $anchorScroll, $location, GenerosService) {
  var COR_PADRAO = '#2E1C74';
  var vm = this;
  vm.sequenciasFamosas = [];
  vm.carregandoSequencias = true;
  vm.erroSequencias = false;
  vm.minhaSequencia = {};
  vm.isSearching = false;
  vm.showSearchResultsCount = false;
  vm.esfigeSpeech =  "";
  vm.musics = [];
  vm.generos = [];
  vm.erroGeneros = false;
  vm.meuGenero = "";
  vm.novaSequencia = { acordes: '' };
  vm.cadastrando = false;
  vm.mensagem = "";
  vm.erro = "";
  vm.progressbar = ngProgressFactory.createInstance();

  GenerosService.carregar().then(function(generos) {
    vm.generos = generos;
  }, function() {
    vm.erroGeneros = true;
  });

  var carregarSequencias = function() {
    vm.carregandoSequencias = true;
    vm.erroSequencias = false;
    return $http.get('sequencias').then(function(response) {
      vm.sequenciasFamosas = response.data.map(function(sequencia) {
        return {
          index: sequencia.id,
          id: sequencia.id,
          acordes: sequencia.acordes.map(function(acorde) {
            return { acorde: acorde, cor: COR_PADRAO };
          })
        };
      });
      vm.carregandoSequencias = false;
    }, function() {
      vm.carregandoSequencias = false;
      vm.erroSequencias = true;
    });
  };

  carregarSequencias();

  vm.temAcorde = function(acorde) {
    if (vm.minhaSequencia.acordes) {
      return (vm.minhaSequencia.acordes.indexOf(acorde) > -1);
    } else {
      return false;
    }
  }

  var createChordsString = function(chords) {
    var str = "";
    for (var i = 0; i < chords.length; i++) {
      str = str.concat(chords[i].acorde, ',');
    }
    return str.substring(0, str.length-1);
  }

  vm.cadastrarSequencia = function() {
    vm.mensagem = "";
    vm.erro = "";
    vm.cadastrando = true;

    $http.post('sequencias', {
      acordes: vm.novaSequencia.acordes
    }).then(function(response) {
      vm.cadastrando = false;
      if (response.status === 200 && response.data.duplicada) {
        vm.mensagem = "Sequência já existente.";
      } else {
        vm.mensagem = "Sequência cadastrada com sucesso!";
      }
      vm.novaSequencia = { acordes: '' };
      carregarSequencias();
    }, function(response) {
      vm.cadastrando = false;
      if (response.status === 400 && response.data && response.data.erro) {
        vm.erro = response.data.erro;
      } else {
        vm.erro = "Não foi possível cadastrar a sequência. Tente novamente.";
      }
    });
  }

  vm.pesquisarPorSequencia = function(sequencia) {
    if (sequencia) {
      vm.minhaSequencia = sequencia;
    }
    vm.progressbar.start();
    vm.esfigeSpeech = "Procurando músicas com base na sequencia...";
    vm.isSearching = true;
    vm.musics = [];

    var apiUrl = "";
    var searchString = "similares?sequencia=".concat(createChordsString(vm.minhaSequencia.acordes));
    if (vm.meuGenero !== "" && vm.meuGenero !== null) {
      searchString += "&generos="+vm.meuGenero;
    }
    $http.get(apiUrl.concat(searchString))
      .success(function(data) {
        vm.progressbar.complete();
        vm.esfigeSpeech = "Encontrei essas músicas";
        vm.isSearching = false;
        vm.showSearchResultsCount = true;
        vm.musics = data;
      })
      .error(function(data) {
        vm.esfigeSpeech = "Ops! Algo errado.";
        vm.isSearching = false;
        vm.showSearchResultsCount = false;
      });
  }

  vm.limparPesquisa = function() {
    vm.minhaSequencia = {};
    vm.musics = [];
  }

  vm.goToLirics = function(music) {
    $window.open(music.url);
  };

  vm.goToResults = function() {
    vm.showSearchResultsCount = false;
    $("body").animate({scrollTop: $("#results").offset().top}, "slow");
  };
});
