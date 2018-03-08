App.controller('ListingController',['$scope','$http','$filter','$compile',
  function($scope,$http,$filter,$compile){

      $scope.listings = [];
      $scope.currentPage = 1;
      $scope.noOfRecords = 0;
      $scope.perPage = 10;
      $scope.noOfPages = 0;

      $scope.filterListings = function(){
        $http.post("/listings_by_make_and_model.json", {
          data: {"make_id":$('#make_info_make').val(),"model_id":$('#model_info_model').val(),"page" : 1, "zip" : this.zip, "year": this.year }
        }).success(function(data, status) {
          $scope.listings = data.listings;
          $scope.noOfRecords = data.total_records;
          $scope.perPage = 10;
          $scope.noOfPages = Math.floor($scope.noOfRecords/$scope.perPage);
          $scope.currentPage = 1;
          $scope.pag_html = data.pag_html;
          $('.row.listings-detail-info').html($compile($scope.pag_html)($scope));
          var remaining_entries = $scope.noOfRecords % $scope.perPage;
          if(remaining_entries>0)
            $scope.noOfPages++;
        });
      }

        $scope.setPage = function(obj){
          if((obj.currentTarget.innerHTML === '«' && $scope.currentPage==1) || (obj.currentTarget.innerHTML === '»' && $scope.currentPage==$scope.noOfPages) || $scope.currentPage.toString() == obj.currentTarget.innerHTML )
            return false;
          else{
            if(obj.currentTarget.innerHTML === '»'){
                $scope.currentPage++;
            }
            else if(obj.currentTarget.innerHTML === '«'){
              $scope.currentPage--;
            }
            else{
              $scope.currentPage = parseInt(obj.currentTarget.innerHTML);
            }
            var year='';
            if($('#lf_listing_year').val()=="")
              year = $("#year_info_year").val();
            else
              year = $('#lf_listing_year').val()
            $http.post("/listings_by_make_and_model.json", {
              data: {"make_id":$('#make_info_make').val(),"model_id":$('#model_info_model').val(),"page" : $scope.currentPage,"zip" : this.zip, "year": year }
            }).success(function(data, status) {
              $scope.listings = data.listings;
              $scope.noOfRecords = data.total_records;
              $scope.perPage = 10;
              $scope.noOfPages = Math.floor($scope.noOfRecords/$scope.perPage);
              var remaining_entries = $scope.noOfRecords % $scope.perPage;
              if(remaining_entries>0)
                $scope.noOfPages++;
              $scope.pag_html = data.pag_html;
              $('.row.listings-detail-info').html($compile($scope.pag_html)($scope));
            });
          }
        }
  }
]);

$.expr[":"].containsExact = function (obj, index, meta, stack) {
  return (obj.textContent || obj.innerText || $(obj).text() || "") == meta[3];
};

