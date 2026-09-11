/*   developer: bil4i3n, contact:: fb.com/bil.jx   */

// $(document).bind("contextmenu",function(e){ e.preventDefault(); }); 
// $(document).keydown(function(ev) { ev = ev || window.event;  kc = ev.keyCode || ev.which;  if((ev.ctrlKey || ev.metaKey) && kc) { if(kc == 99 || kc == 67 || kc == 88 || kc == 120 || kc == 85 || kc == 117 || kc == 73 || kc == 105) { return false; } } });

var bil_gSkin = '/include/web_skins/thachi/';

function btnGetGiftCode(){
	utils.WaitLoading();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=getgiftcode",
		data: {KeySend: 'GetGiftCode_GFwhkj6EW',KeyVerify: 'GetGiftCode_jhew4654'},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingUnload();
			if(data.ReceivedGetGiftCode == 35165){
				if(data.ReceivedGetGiftCode_Check == 351651){
					return utils.ErrorMessagePopup("<a style='color:red;'>Bạn đã nhận gói phần thưởng này rồi, không thể nhận lại lần nữa!</a>");
				}
				else{
					if(data.ReceivedGetGiftCode_Check == 351652){
						return utils.ErrorMessagePopup("<a style='color:#20ff20;'>Nhận thưởng GiftCode thành công, bạn có thể thoát game đăng nhập lại, mở Cẩm nang tân thủ để tiến hành nhận thưởng!</a>");
					}
					else{
						if(data.ReceivedGetGiftCode_Check == 351653){
							return utils.ErrorMessagePopup("<a href='/acc.php' style='color:yellow;'><strong>Quý nhân sĩ chưa đăng nhập tài khoản, nhấn vào đây để chuyển tới trang đăng nhập sau đó quay lại đây để nhận thưởng!</strong></a>");
						}
					}
				}
			}
			else{
				return utils.ErrorMessagePopup("Hệ thống đang bận. Vui lòng quay lại sau!");
			}
		},
		error: function () {
			utils.WaitLoadingUnload();
			return utils.ErrorMessagePopup("Hệ thống đang bận. Vui lòng quay lại sau!");
		}
	});
}

function ErrorPage(Sel, c_Msg){
    if(Sel == 0){
        $('body').append("<div id='ErrorPage' onclick='ErrorPage(1)' style='width: 100%;height: 100%;position: fixed;top: 0;background: rgba(0, 0, 0, 0.68);'><div style='position: fixed;text-align: center;width: 779px;background: #fff;top: 0;padding: 36px 0;border-radius: 12px;margin: 20% 0 0 20%;'><a>"+ c_Msg +"</a></div><div>");
    }
    if(Sel==1){
        $('#ErrorPage').remove();
    }
}

window.utils = {
	WaitLoading: function(){
		this.WaitLoadingUnload();
		$("body").append("<div id='WaitLoading'><img src='/include/web_skins/default/images/loading.gif'></img></div>");
	},
	WaitLoadingUnload: function(){
		$("#WaitLoading").remove();
	},
	ErrorMessagePopup :function(text){
		this.ErrorMessagePopupUn();
		$('body').append('<div id=ErrorMessagePopup style=position:fixed;top:0;width:100%;text-align:center;height:100%;background:rgba(0,0,0,0.68);z-index:99999;><div style=margin:auto;padding-top:12px;padding-bottom:12px;background:rgba(255,255,255,0.23);border-radius:8px;color:#11AF00;margin-top:18%;font-size:14px;><a style=color:#fff;>' + text + '</a><br><input style=text-align:center;outline:0;background:#fd7727;border:none;color:#fff;height:29px;width:79px;border-radius:4px;padding-left:8px;margin-top:9px;cursor:pointer; type="submit" value=OK onclick=utils.ErrorMessagePopupUn()></div></div>');
	},
	ErrorMessagePopupUn: function(){
		$('#ErrorMessagePopup').remove();
	},
}
/*   developer: bil4i3n, contact:: fb.com/bil.jx   */

























