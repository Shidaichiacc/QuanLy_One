/*   developer: bil4i3n, contact:: fb.com/bil.jx   */

var coin2day = {
	process_api : '/include/web_skins/common/coin2day.php',
	ratio : 0,
	currency_unit: 'COIN',
	
	elements : {
		content: 'coin2day1',
		main : 'coin2day2',
		menu_date : 'coin2day3',
		menu_time : 'coin2day4',
		value_coin_date : 'coin2day5',
		value_coin_time : 'coin2day6',
		convert_date : 'coin2day7',
		convert_time : 'coin2day8',
		submit_message : 'coin2day11',
		currency_unit_d : 'coin2day12d',
		currency_unit_t : 'coin2day12t',
	},
	
	form : {
		summary : 
			'<div id="coin2day2" style="position: fixed;left: 0;top: 0;width: 100%;height: 100%;background: #00000073;z-index: 999;font-size: 13px;">'+
				'<style>'+
					'.coin2day_mn_a1{color: #0093ff;font-size: 13px;display: inline-block;margin: 0 12px;cursor: pointer;padding: 8px 20px;border-radius: 8px;border-bottom-left-radius: 0;border-bottom-right-radius: 0;user-select: none;}'+
					'.coin2day_mn_a1.active{background: white;border: 1px solid #e2e2e2;border-bottom: 1px solid white;color: black;cursor: no-drop;}'+
				'</style>'+
				'<div style="background: #f7f7f7;width: 40%;height: 320px;margin: 5% auto;min-width: 540px;border-radius: 8px;">'+
					'<div style="border-bottom: 1px solid #e2e2e2;padding-top: 15px;margin: 0 25px;">'+
						'<a id="coin2day3" onclick="coin2day.ChangeExpiresDate()" class="coin2day_mn_a1" >Đổi <span id="coin2day12d"></span>ngày chơi</a>'+
						'<a id="coin2day4" onclick="coin2day.ChangeExpiresTime()" class="coin2day_mn_a1" >Đổi <span id="coin2day12t"></span>giờ chơi</a>'+
						'<a onclick="coin2day.Close()" style="float: right;background: #e2e2e2;border-radius: 50%;width: 20px;color: red;cursor: pointer;text-indent: 6px;font-weight: bold;">X</a>'+
					'</div>'+
					'<div id="coin2day1" style="margin: 15px 25px 0;line-height: 2;"></div>'+
				'</div>'+
			'</div>'
	},
	
	converter : {
		Number2DateTime : function(_in_value, _in_group){
			var local_date = {day: 0, hour: 0, min: 0, sec: 0};
			
			if(_in_value && _in_value > 0){
				if(_in_group.day && Math.floor(_in_value/86400) > 0){
					local_date.day = Math.floor(_in_value/86400);
					_in_value -= local_date.day * 86400;
				}
				
				if(_in_group.hour && Math.floor(_in_value/3600) > 0){
					local_date.hour = Math.floor(_in_value/3600);
					_in_value -= local_date.hour * 3600;
				}
				
				if(_in_group.min && Math.floor(_in_value/60) > 0){
					local_date.min = Math.floor(_in_value/60);
					_in_value -= local_date.min * 60;
				}
				
				local_date.sec = _in_value;
			}
			
			return local_date;
		}
	},
	
	submit : {
		CoinToDate : function(){
			this.Message('<span style="color:orange;">đang xử lý yêu cầu, vui lòng đợi trong giây lát...</span>');
			
			$.ajax({
				type: "POST",cache: false,url: coin2day.process_api,dataType: "json",data: {r: 'sd', v: $('#'+coin2day.elements.value_coin_date).val()},
				success: function (data) {
					if(data.r == 1) return coin2day.ChangeExpiresDate();
					else return coin2day.submit.Message('<span style="color:red;">'+data.d+'</span>');
				},
				error: function () {return coin2day.submit.Message('<span style="color:red;">hệ thống đang bận, vui lòng thử lại sau!</span>');}
			});
		},
		
		CoinToTime : function(){
			this.Message('<span style="color:orange;">đang xử lý yêu cầu, vui lòng đợi trong giây lát...</span>');
			
			$.ajax({
				type: "POST",cache: false,url: coin2day.process_api,dataType: "json",data: {r: 'st', v: $('#'+coin2day.elements.value_coin_time).val()},
				success: function (data) {
					if(data.r == 1) return coin2day.ChangeExpiresTime();
					else return coin2day.submit.Message('<span style="color:red;">'+data.d+'</span>');
				},
				error: function () {return coin2day.submit.Message('<span style="color:red;">hệ thống đang bận, vui lòng thử lại sau!</span>');}
			});
		},
		
		Message : function(_in_message){
			return $('#'+coin2day.elements.submit_message).html(_in_message);
		}
	},
	
	Open_Payment : function(){
		var local_funtion = [
			['AccountInfoAllData', 3],
			['fF', 3]
		];
		
		this.Close();
		
		for(_index = 0; _index < local_funtion.length; _index++){
			if(eval('typeof '+local_funtion[_index][0]) === 'function')
				return eval(local_funtion[_index][0]+'('+local_funtion[_index][1]+');')
		}
		
		return;
	},
	
	Open : function(){
		$('body').append(this.form.summary);
		return this.ChangeExpiresDate();
	},
	
	Close : function(){
		return $('#'+this.elements.main).remove();
	},
	
	ChangeExpiresDate : function(){
		this.MessageProcessing();
		$('#'+this.elements.menu_date).addClass('active');
		$('#'+this.elements.menu_time).removeClass('active');
		
		$.ajax({
			type: "POST",cache: false,url: coin2day.process_api,dataType: "json",data: {r: 'gd'},
			success: function (data) {
				if(data.r == 1 && data.ratio){
					$('#'+coin2day.elements.content).html(data.d);
					coin2day.ratio = data.ratio;
					
					if(data.currency_unit)
						coin2day.set_data.CurrencyUnit(data.currency_unit);
					
					return;
				}
				else return coin2day.MessageError(data.d);
			},
			error: function () {
				return coin2day.MessageError("Hệ thống đang bận. Vui lòng thử lại sau!");
			}
		});
	},
	
	ChangeExpiresTime : function(){
		this.MessageProcessing();
		$('#'+this.elements.menu_time).addClass('active');
		$('#'+this.elements.menu_date).removeClass('active');

		$.ajax({
			type: "POST",cache: false,url: coin2day.process_api,dataType: "json",data: {r: 'gt'},
			success: function (data) {
				if(data.r == 1 && data.ratio){
					$('#'+coin2day.elements.content).html(data.d);
					coin2day.ratio = data.ratio;
					
					if(data.currency_unit)
						coin2day.set_data.CurrencyUnit(data.currency_unit);
					
					return;
				}
				else return coin2day.MessageError(data.d);
			},
			error: function () {
				return coin2day.MessageError("Hệ thống đang bận. Vui lòng thử lại sau!");
			}
		});
	},
	
	ConvertCoin2Date : function(){
		var local_value_input = $('#'+this.elements.value_coin_date).val();
		var local_date = this.converter.Number2DateTime(local_value_input * this.ratio, {day:true, hour:true, min:true});
		
		return $('#'+this.elements.convert_date).html('đổi '+(local_value_input?local_value_input:0)+' '+this.currency_unit+' thành'+(local_date.day > 0 ? ' '+local_date.day + ' ngày' : '')+(local_date.hour > 0 ? ' '+local_date.hour + ' giờ' : '')+(local_date.min > 0 ? ' '+local_date.min + ' phút' : '')+(local_date.sec > 0 ? ' '+local_date.sec + ' giây' : ' 0 giây')+' (HSD)');
	},
	
	ConvertCoin2Time : function(){
		var local_value_input = $('#'+this.elements.value_coin_time).val();
		var local_date = this.converter.Number2DateTime(local_value_input * this.ratio, {day:false, hour:true, min:true});
		
		return $('#'+this.elements.convert_time).html('đổi '+(local_value_input?local_value_input:0)+' '+this.currency_unit+' thành'+(local_date.day > 0 ? ' '+local_date.day + ' ngày' : '')+(local_date.hour > 0 ? ' '+local_date.hour + ' giờ' : '')+(local_date.min > 0 ? ' '+local_date.min + ' phút' : '')+(local_date.sec > 0 ? ' '+local_date.sec + ' giây' : ' 0 giây')+' (giờ chơi)');
	},
	
	set_data : {
		CurrencyUnit : function(_in_value){
			if(typeof _in_value === 'undefined')
				return;
			
			coin2day.currency_unit = _in_value;
			
			$('#'+coin2day.elements.currency_unit_d).html(coin2day.currency_unit+' sang ');
			$('#'+coin2day.elements.currency_unit_t).html(coin2day.currency_unit+' sang ');
			
			return;
		}
	},
	
	MessageError : function(_in_message){
		return $('#'+this.elements.content).html('<a style="color: red;display: block;text-align: center;margin-top: 10%;">'+_in_message+'</a');
	},
	MessageProcessing : function(){
		return $('#'+this.elements.content).html('<a style="color: black;display: block;text-align: center;margin-top: 10%;">đang xử lý yêu cầu, vui lòng đợi trong giây lát...</a');
	}
}

/*   developer: bil4i3n, contact:: fb.com/bil.jx   */















