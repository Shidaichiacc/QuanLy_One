/*   developer: bil4i3n, contact:: fb.com/bil.jx   */

var bil_gSkin = '/include/web_skins/thachi/';

function btnCheckLoginAjax() {
	var username = utils.convertUTFStr($('#LoginUsername').val());
	var password = utils.convertUTFStr($("#LoginPassword").val());
	var captcha = $("#LoginCaptcha").val();
	if (username == null || username == "") {
		utils.ErrorMessage("Bạn vui lòng nhập tên tài khoản");
		return;
	}
	if (username.length < 4 || username.length > 24) {
		$("#LoginUsername").focus();
		utils.ErrorMessage('Tên tài khoản từ 4-16 ký tự');
		return;
	}
	if (password == null || password == "") {
		utils.ErrorMessage("Bạn vui lòng nhập mật khẩu");
		return;
	}
	if (captcha == '') {
		utils.ErrorMessage('Bạn vui lòng nhập mã xác nhận');
		return;
	}
	if (captcha.length != 4) {
		utils.ErrorMessage('Mã xác nhận không hợp lệ');
		return;
	}
	utils.WaitLoading();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=loginajax",
		data: {
			userName: username,
			pass: password,
			captcha: captcha,
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingUnload();
			if(data.ReceivedLogin == 1234){
				$("#MenuBar_DangNhap").html('<p class="Menu" onclick="LogOutFromMenuBar()">Đăng xuất</p>');
				$(".FormLogin").empty();
				$(".FormLogin").append(data.ReceivedLoginData);
				return;
			}
			else{
				return utils.ErrorMessage(data.MsgError);
			}
		},
		error: function () {
			utils.WaitLoadingUnload();
			utils.ErrorMessage("Các khai báo không hợp lệ!");
		}
	});
}

function btnNapThe(){
	$(function(){
		if($('#AccountLoginOK').val() == null || $('#AccountLoginOK').val() == ""){
			return utils.ErrorMessage("Bạn chưa đăng nhập, không thể nạp thẻ!");
		}
		else{
			utils.WaitLoading();
			$.ajax({
				type: "POST",
				cache: false,
				url: bil_gSkin+"skin_account.php?action=viewaccountallinfo",
				data: {KeySend: 'ViewAccountAllInfo',KeyRequestVerify: 'ViewAccountAllInfo_kgjSLKGkj4J849JS734jk'},
				dataType: "json",
				success: function (data) {
					utils.WaitLoadingUnload();
					if(data.ReceivedDataOfAccountInfo == 15485487551){
						$("body").append(data.ReceivedDataOfAccountInfoOK);
						AccountInfoAllData(3);
						return;
					}
					else{
						return utils.ErrorMessagePopup(data.MsgError);
					}
				},
				error: function () {
					utils.WaitLoadingUnload();
					return utils.ErrorMessagePopup("Các khai báo không hợp lệ!");
				}
			});
		}
	});
}

function btnLogOutAjax(){
	utils.WaitLoading();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=logoutajax",
		data: {KeyLogout: 'LogOutAjax',KeyLogoutVerify: 'LogOutAjax_HWUNSKNDF1126hqw2'},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingUnload();
			if(data.ReceivedLogout == 1111){
				// $(".FormLogin>div").remove();
				// $(".FormLogin>input").remove();
				// $(".FormLogin>a").remove();
				// $(".FormLogin>img").remove();
				return utils.ErrorMessagePopup("Đăng xuất tài khoản thành công!");
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

function btnOpenPopupRegisterAjax(){
	utils.WaitLoading();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=registerajax",
		data: {KeyRegister: 'registerajax',KeyRegisterVerify: 'Register_KJFGU34788jhkJ'},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingUnload();
			if(data.ReceivedRegisterAjax == 12351){
				$("#OpenPopup").remove();
				$("body").append(data.ReceivedDataRegister);
				return;
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

function ClosePopupRegisterAjax(){
	return $("#OpenPopup").remove();
}

function RegisterAjaxPopupSendData(){
	var username_ori = $('#RegisterPopupAjaxUserName').val();
	var password_ori = $('#RegisterPopupAjaxPassword').val();
	var passwordRe_ori = $('#RegisterPopupAjaxRePassword').val();
	
	var username = utils.convertUTFStr(username_ori);
	var password = utils.convertUTFStr(password_ori);
	var repassword = utils.convertUTFStr(passwordRe_ori);
	
	if(username_ori !== username)
		return utils.ErrorMessageRegisterPopupAjax("Tên TK có chứa các ký tự không hợp lệ!");
	if(password_ori !== password)
		return utils.ErrorMessageRegisterPopupAjax("Mật khẩu có chứa các ký tự không hợp lệ!");
	if(passwordRe_ori !== repassword)
		return utils.ErrorMessageRegisterPopupAjax("Xác nhận MK có chứa các ký tự không hợp lệ!");
	
	var numberphone = utils.convertUTFStr($("#RegisterPopupAjaxNumberPhone").val());
	var captcha = $("#RegisterPopupAjaxCodeVerify").val();
	if (username == null || username == "") {
		utils.ErrorMessageRegisterPopupAjax("Bạn vui lòng nhập tên tài khoản");
		return;
	}
	if (username.length < 4 || username.length > 24) {
		$("#RegisterPopupAjaxUserName").focus();
		utils.ErrorMessageRegisterPopupAjax('Tên tài khoản từ 4-24 ký tự');
		return;
	}
	if (password == null || password == "") {
		utils.ErrorMessageRegisterPopupAjax("Bạn vui lòng nhập mật khẩu");
		return;
	}
	if (repassword == null || repassword == "") {
		utils.ErrorMessageRegisterPopupAjax("Bạn vui lòng nhập lại mật khẩu");
		return;
	}
	if (captcha == '') {
		utils.ErrorMessageRegisterPopupAjax('Bạn vui lòng nhập mã xác nhận');
		return;
	}
	if (captcha.length != 4) {
		utils.ErrorMessageRegisterPopupAjax('Mã xác nhận không hợp lệ');
		return;
	}
	if(password != repassword){
		utils.ErrorMessageRegisterPopupAjax('Mật khẩu nhập lại không khớp');
		return;
	}
	if(numberphone == null || numberphone == ''){
		return utils.ErrorMessageRegisterPopupAjax("Số điện thoại không được để trống");
	}
	if(numberphone.length > 11){
		return utils.ErrorMessageRegisterPopupAjax("Số điện thoại không được chấp nhận");
	}
	utils.WaitLoading();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=registerpopupajax&writesys=registerdatasend",
		data: {KeyRegister: 'RegisterPopupAjax',
			KeyRegisterVerify: 'RegisterPopupAjax_KJHGkjfdgh457ht6548HGJHhgf6',
			RegisterUserName:username,
			RegisterPassWord:password,
			ResisgerRePassWord:repassword,
			RegisterCaptcha:captcha,
			RegisterNumberPhone:numberphone
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingUnload();
			if(data.ReceivedRegisterPopupAjaxValue == 15498951){
				$("#RegisterPopupAjaxSentError").empty();
				$("#RegisterPopupAjaxSentError").append(data.ReceivedDataRegisterPopupAjaxOK);
				return;
			}
			else{
				return utils.ErrorMessageRegisterPopupAjax(data.MsgError);
			}
		},
		error: function () {
			utils.WaitLoadingUnload();
			return utils.ErrorMessageRegisterPopupAjax("Các khai báo không hợp lệ!");
		}
	});
}

function ViewAccountAllInfo(){
	utils.WaitLoading();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=viewaccountallinfo",
		data: {KeySend: 'ViewAccountAllInfo',KeyRequestVerify: 'ViewAccountAllInfo_kgjSLKGkj4J849JS734jk'},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingUnload();
			if(data.ReceivedDataOfAccountInfo == 15485487551){
				$("body").append(data.ReceivedDataOfAccountInfoOK);
				AccountInfoAllData(1);
				return;
			}
			else{
				return utils.ErrorMessagePopup(data.MsgError);
			}
		},
		error: function () {
			utils.WaitLoadingUnload();
			return utils.ErrorMessagePopup("Hệ thống đang bận, vui lòng quay lại sau!");
		}
	});
}

function ClosePopupViewAccountAllInfo(){
	return $("#OpenPopupViewAccountAllInfo").remove();
}

function AccountInfoAllData_ChangeMenuIconBar(Sel){
	if (Sel == 2){
		$("#MenuBar_DangKy").removeClass("Menu_isCurrent ");
		$("#MenuBar_TaiKhoan").addClass("Menu_isCurrent ");
		$("#MenuBar_NapThe").removeClass("Menu_isCurrent ");
		$("#MenuBar_CapNhat").removeClass("Menu_isCurrent ");
		$("#MenuBar_LichSu").removeClass("Menu_isCurrent ");
	}
	if(Sel == 3){
		$("#MenuBar_DangKy").removeClass("Menu_isCurrent ");
		$("#MenuBar_TaiKhoan").removeClass("Menu_isCurrent ");
		$("#MenuBar_NapThe").addClass("Menu_isCurrent ");
		$("#MenuBar_CapNhat").removeClass("Menu_isCurrent ");
		$("#MenuBar_LichSu").removeClass("Menu_isCurrent ");
	}
	if(Sel == 4){
		$("#MenuBar_DangKy").removeClass("Menu_isCurrent ");
		$("#MenuBar_TaiKhoan").removeClass("Menu_isCurrent ");
		$("#MenuBar_NapThe").removeClass("Menu_isCurrent ");
		$("#MenuBar_CapNhat").addClass("Menu_isCurrent ");
		$("#MenuBar_LichSu").removeClass("Menu_isCurrent ");
	}
	if(Sel == 5){
		$("#MenuBar_DangKy").removeClass("Menu_isCurrent ");
		$("#MenuBar_TaiKhoan").removeClass("Menu_isCurrent ");
		$("#MenuBar_NapThe").removeClass("Menu_isCurrent ");
		$("#MenuBar_CapNhat").removeClass("Menu_isCurrent ");
		$("#MenuBar_LichSu").addClass("Menu_isCurrent ");
	}
}

function AccountInfoAllData(Sel){
	if(Sel == 1){
		var Action = "viewaccountallinforequest";
		var Request = "alldata";
		var KeySend = "ViewAccountAllInfoRequest";
		var KeyRequestVerify = "ViewAccountAllInfo_jgjure38uhHJyu79Jy736H6t";
		ReceivedDataOfAccountInfo4RequestAllData = 332457465;
	}
	else{
		if(Sel == 2){
			var Action = "viewaccountallinforequest";
			var Request = "thongtintaikhoan";
			var KeySend = "ViewAccountAllInfoRequest_ThongTinTaiKhoan";
			var KeyRequestVerify = "ViewAccountAllInfoRequest_ThongTinTaiKhoan_KKJHg773HKJ79jh78t2JH";
			ReceivedDataOfAccountInfo4RequestAllData = 54528868;
		}
		else{
			if(Sel == 3){
				var Action = "naptiendongtaikhoan";
				var Request = "checkcardstatus";
				var KeySend = "NapTheDoiTienDong";
				var KeyRequestVerify = "NapTheDoiTienDong_KJHiuy776iuhBNJHg36hjkH";
				ReceivedDataOfAccountInfo4RequestAllData = 6895797;
			}
			else{
				if(Sel == 4){
					var Action = "editaccountinfo";
					var Request = "capnhatthongtintaikhoan";
					var KeySend = "CapNhatAccountInfomation";
					var KeyRequestVerify = "CapNhatAccountInfomation_hhgyKJft7hHggte7Li";
					ReceivedDataOfAccountInfo4RequestAllData = 514587;
				}
				else{
					if(Sel == 5){
						var Action = "viewaccountallinforequest";
						var Request = "historycardgame";
						var KeySend = "ViewHistoryCard";
						var KeyRequestVerify = "ViewHistoryCard_kjNjh77hjJH77329KJH";
						ReceivedDataOfAccountInfo4RequestAllData = 548158;
					}
				}
			}
		}
	}
	$("#MainAccountAllInfo>div").remove();
	utils.WaitLoadingAccountInfo();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=" + Action + "&request=" + Request + "",
		data: {UserNameRequest:$('#UserName4Request').val(),KeySend: KeySend,KeyRequestVerify: KeyRequestVerify},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingAccountInfoUnLoad();
			if(data.ReceivedDataOfAccountInfo4RequestAllData == ReceivedDataOfAccountInfo4RequestAllData){
				AccountInfoAllData_ChangeMenuIconBar(Sel);
				if(data.ReceivedDataOfAccountInfo4RequestAllData == 514587 && KeySend == "CapNhatAccountInfomation"){
					$("#InfoAccount").empty();
					$("#InfoAccount").append(data.ReceivedDataOfAccountInfo4RequestAllDataOK);
					AccountInfoAllDataEditInfo(1);
					return;
				}
				else{
                    $("#InfoAccount").empty();
					$("#InfoAccount").append(data.ReceivedDataOfAccountInfo4RequestAllDataOK);
					return;
				}
			}
			else{
				return ClosePopupViewAccountAllInfo();
			}
		},
		error: function () {
			utils.WaitLoadingAccountInfoUnLoad();
			return utils.ErrorMessage("Bạn cần đăng nhập để sử dụng tính năng này!");
		}
	});
}

function AccountInfoTransfer(){
	return utils.ErrorMessagePopup("Hiện tại tính năng chuyển Tiền đồng cho tài khoản khác đang được hoàn thiện!");
}

function LogOutFormPopupAccountInfo(){
	utils.WaitLoadingAccountInfo();
	ClosePopupViewAccountAllInfo();
	utils.WaitLoadingAccountInfoUnLoad();
	btnLogOutAjax();
	return;
}

function LogOutFromMenuBar(){
	LogOutFormPopupAccountInfo();
	$('body').append("<META HTTP-EQUIV='refresh' CONTENT='1; URL=/acc.php'>");
}

function NapTheBangTaiKhoanNganHang(Sel){
	if(Sel == 1){
		return utils.ErrorMessagePopup("Hiện tại tính năng nạp tiền đồng bằng thẻ ATM/VISA đang được phát triển!");
	}
	else{
		if(Sel == 2){
			return utils.ErrorMessagePopup("Hiện tại tính năng nạp tiền đồng bằng tài khoản Điện tử đang được phát triển!");
		}
	}
}

function btnSendCardInfo2Server(){
	var SendInfoCardAccount = utils.convertUTFStr($('#SendInfoCard_Account').val());
	var SendInfoCardCardType = utils.convertUTFStr($('#NapTienDongLoaiThe').val());
	var SendInfoCardCardSERI = utils.convertUTFStr($('#NapTienDongSeriThe').val());
	var SendInfoCardCardCODE = utils.convertUTFStr($('#NapTienDongMaThe').val());
	var SendInfoCardCardCODEVerify = utils.convertUTFStr($('#NapTienDongMaXacNhan').val());
	if (SendInfoCardAccount == null || SendInfoCardAccount == "") {
		utils.MsgErrorNapTheTienDong("Bạn chưa đăng nhập, bạn cần đăng nhập lại để nạp thẻ!");
		return;
	}
	if (SendInfoCardCardType == null || SendInfoCardCardType == "") {
		utils.MsgErrorNapTheTienDong("Bạn vui lòng chọn Loại thẻ!");
		return;
	}
	if (SendInfoCardCardSERI == null || SendInfoCardCardSERI == "") {
		utils.MsgErrorNapTheTienDong("Bạn vui lòng nhập số Seri thẻ!");
		return;
	}
	if (SendInfoCardCardCODE == null || SendInfoCardCardCODE == "") {
		utils.MsgErrorNapTheTienDong("Bạn vui lòng nhập Mã thẻ!");
		return;
	}
	if (SendInfoCardCardCODEVerify == null || SendInfoCardCardCODEVerify == "") {
		utils.MsgErrorNapTheTienDong("Bạn vui lòng Mã xác nhận!");
		return;
	}
	if (SendInfoCardCardCODEVerify.length != 4) {
		utils.MsgErrorNapTheTienDong("Mã xác nhận không hợp lệ, bạn vui lòng nhập lại!");
		return;
	}
	utils.clearErrorMessage("MsgErrorNapThe");
	utils.WaitLoadingCheckCardInfo();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=sendcardinfo2server&received=checkcardstatus",
		data: {
			SendInfoCardAccount:SendInfoCardAccount,
			SendInfoCardCardType:SendInfoCardCardType.toUpperCase(),
			SendInfoCardCardSERI:SendInfoCardCardSERI,
			SendInfoCardCardCODE:SendInfoCardCardCODE,
			SendInfoCardCardCODEVerify:SendInfoCardCardCODEVerify,
			KeySend: "SendCardInfo2Server",
			KeyRequestVerify: "CheckCardStatus_JNFG73HKJGH3879",
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingCheckCardInfoUnload();
			if(data.ReceivedDataOfCheckCardData == 6863779){
				$("#FormInputCardInfo").html(data.ReceivedDataOfCheckCardOK);
				$("#CountCoinAccount").empty();
				$("#CountCoinAccount").append(data.ReceivedDataOfCheckCardOK_CountCoin);
				return;
			}
			else{
				return utils.MsgErrorNapTheTienDong(data.MsgError);
			}
		},
		error: function () {
			utils.WaitLoadingCheckCardInfoUnload();
			return utils.MsgErrorNapTheTienDong("Thông tin bạn cung cấp không khả dụng, phiền bạn thử lại sau!");
		}
	});
}

function AccountInfoAllDataEditInfo(Sel){
	if(Sel == 1){
		var KeySend = "CapNhatAccountInfomation_EditPassword1";
		var KeyRequestVerify = "CapNhatAccountInfomation_EditPassword1_2tghhgyKrG3Jft7hHggte7Li";
		ReceivedDataOfAccountInfo4RequestAllData = 514471;
		$("#DoiMatKhau1").addClass("EdIf_p1_isCurrent ");
		$("#DoiMatKhau2").removeClass("EdIf_p1_isCurrent ");
		$("#DoiCauHoiBM").removeClass("EdIf_p1_isCurrent ");
		$("#DoiDiaChiEmail").removeClass("EdIf_p1_isCurrent ");
		$("#DoiTTTaiKhoan").removeClass("EdIf_p1_isCurrent ");
	}
	if(Sel == 2){
		var KeySend = "CapNhatAccountInfomation_EditPassword2";
		var KeyRequestVerify = "CapNhatAccountInfomation_EditPassword2_j8H7ijJJIHU8";
		ReceivedDataOfAccountInfo4RequestAllData = 514472;
		$("#DoiMatKhau1").removeClass("EdIf_p1_isCurrent ");
		$("#DoiMatKhau2").addClass("EdIf_p1_isCurrent ");
		$("#DoiCauHoiBM").removeClass("EdIf_p1_isCurrent ");
		$("#DoiDiaChiEmail").removeClass("EdIf_p1_isCurrent ");
		$("#DoiTTTaiKhoan").removeClass("EdIf_p1_isCurrent ");
	}
	if(Sel == 3){
		var KeySend = "CapNhatAccountInfomation_EditAnswerQuestion";
		var KeyRequestVerify = "CapNhatAccountInfomation_EditAnswerQuestion_JHu73jkJJHl9";
		ReceivedDataOfAccountInfo4RequestAllData = 514473;
		$("#DoiMatKhau1").removeClass("EdIf_p1_isCurrent ");
		$("#DoiMatKhau2").removeClass("EdIf_p1_isCurrent ");
		$("#DoiCauHoiBM").addClass("EdIf_p1_isCurrent ");
		$("#DoiDiaChiEmail").removeClass("EdIf_p1_isCurrent ");
		$("#DoiTTTaiKhoan").removeClass("EdIf_p1_isCurrent ");
	}
	if(Sel == 4){
		var KeySend = "CapNhatAccountInfomation_EditEmail";
		var KeyRequestVerify = "CapNhatAccountInfomation_EditEmail_kjKLDSHg7hjy29h";
		ReceivedDataOfAccountInfo4RequestAllData = 514474;
		$("#DoiMatKhau1").removeClass("EdIf_p1_isCurrent ");
		$("#DoiMatKhau2").removeClass("EdIf_p1_isCurrent ");
		$("#DoiCauHoiBM").removeClass("EdIf_p1_isCurrent ");
		$("#DoiDiaChiEmail").addClass("EdIf_p1_isCurrent ");
		$("#DoiTTTaiKhoan").removeClass("EdIf_p1_isCurrent ");
	}
	if(Sel == 5){
		var KeySend = "CapNhatAccountInfomation_EditInfo";
		var KeyRequestVerify = "CapNhatAccountInfomation_EditInfo_jhKJH870jjjh7Hj7h";
		ReceivedDataOfAccountInfo4RequestAllData = 514475;
		$("#DoiMatKhau1").removeClass("EdIf_p1_isCurrent ");
		$("#DoiMatKhau2").removeClass("EdIf_p1_isCurrent ");
		$("#DoiCauHoiBM").removeClass("EdIf_p1_isCurrent ");
		$("#DoiDiaChiEmail").removeClass("EdIf_p1_isCurrent ");
		$("#DoiTTTaiKhoan").addClass("EdIf_p1_isCurrent ");
	}
	var Action = "editaccountinfo";
	var Request = "capnhatthongtintaikhoan";
	$("#FormEditInfoAccount").empty();
	utils.WaitLoadingEditInfo();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=" + Action + "&request=" + Request + "",
		data: {UserNameRequest:$('#UserName4Request').val(),KeySend: KeySend,KeyRequestVerify: KeyRequestVerify},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingEditInfoUnload();
			if(data.ReceivedDataOfAccountInfo4RequestAllData == ReceivedDataOfAccountInfo4RequestAllData){
				$("#FormEditInfoAccount").append(data.ReceivedDataOfAccountInfo4RequestAllDataOK);
				return;
			}
			else{
				return ClosePopupViewAccountAllInfo();
			}
		},
		error: function () {
			utils.WaitLoadingEditInfoUnload();
			return ClosePopupViewAccountAllInfo();
		}
	});
}

function btnSendInfoEditAccount2Server_Pass1(){
	var EditAccountInfomationPass1Old = utils.convertUTFStr($('#EditAccountInfomationPass1Old').val());
	var EditAccountInfomationPass1New = utils.convertUTFStr($('#EditAccountInfomationPass1New').val());
	var EditAccountInfomationPass1NewRe = utils.convertUTFStr($('#EditAccountInfomationPass1NewRe').val());
	var EditAccountInfomationPass1CodeVerify = utils.convertUTFStr($('#EditAccountInfomationPass1CodeVerify').val());
	if (EditAccountInfomationPass1Old == null || EditAccountInfomationPass1Old == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng nhập mật khẩu cấp 1 cũ.");return;
	}
	if (EditAccountInfomationPass1Old.length < 4 || EditAccountInfomationPass1Old.length > 24) {
		utils.MsgErrorEditAccountInfomation('Mật khẩu cũ không đúng!');return;
	}
	if (EditAccountInfomationPass1New == null || EditAccountInfomationPass1New == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng nhập mật khẩu cấp 1 mới.");return;
	}
	if (EditAccountInfomationPass1New.length < 4 || EditAccountInfomationPass1New.length > 24) {
		utils.MsgErrorEditAccountInfomation('Mật khẩu yêu cầu từ 4-24 ký tự và a-z, 0-9!');return;
	}
	if (EditAccountInfomationPass1NewRe == null || EditAccountInfomationPass1NewRe == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng nhập lại mật khẩu mới.");return;
	}
	if (EditAccountInfomationPass1NewRe != EditAccountInfomationPass1New) {
		utils.MsgErrorEditAccountInfomation('Xác nhận mật khẩu mới không chính xác!');return;
	}
	if (EditAccountInfomationPass1CodeVerify.length != 4) {
		utils.MsgErrorEditAccountInfomation('Mã xác nhận không đúng!');return;
	}
	utils.WaitLoadingEditAccountInfo();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=editaccountinfosend_pass1&request=receiveddatacheckinfo",
		data: {
			UserNameRequest:$('#UserName4Request').val(),
			KeySend: "EditAccountInfoSend_Pass1",
			KeyRequestVerify: "EditAccountInfoSend_Pass1_jhjyhfh7HgrhgwyiuHJgghjf87hjgy",
			EditAccountInfomationPass1Old: EditAccountInfomationPass1Old,
			EditAccountInfomationPass1New: EditAccountInfomationPass1New,
			EditAccountInfomationPass1NewRe: EditAccountInfomationPass1NewRe,
			EditAccountInfomationPass1CodeVerify: EditAccountInfomationPass1CodeVerify
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingEditAccountInfoUnload();
			if(data.ReceivedDataOfEditAccountInfo4RequestAllData == 158541){
				$("#NotificationEditInfo").html("<a style='color:#1e6d0c;'>Đã cập nhật thông tin thành công!</a>");
				return AccountInfoAllDataEditInfo(1);
			}
			else{
				return utils.MsgErrorEditAccountInfomation(data.MsgError);
			}
		},
		error: function () {
			utils.WaitLoadingEditAccountInfoUnload();
			return utils.MsgErrorEditAccountInfomation("Các khai báo không hợp lệ! chỉ cho phép các ký tự từ a-z và 0-9.");
		}
	});
}

function btnSendInfoEditAccount2Server_Pass2(){
	var EditAccountInfomationPass2Old = utils.convertUTFStr($('#EditAccountInfomationPass2Old').val());
	var EditAccountInfomationPass2New = utils.convertUTFStr($('#EditAccountInfomationPass2New').val());
	var EditAccountInfomationPass2NewRe = utils.convertUTFStr($('#EditAccountInfomationPass2NewRe').val());
	var EditAccountInfomationPass2CodeVerify = utils.convertUTFStr($('#EditAccountInfomationPass2CodeVerify').val());

	if (EditAccountInfomationPass2New == null || EditAccountInfomationPass2New == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng nhập mật khẩu cấp 2 mới.");return;
	}
	if (EditAccountInfomationPass2New.length < 4 || EditAccountInfomationPass2New.length > 24) {
		utils.MsgErrorEditAccountInfomation('Mật khẩu yêu cầu từ 4-24 ký tự và a-z, 0-9!');return;
	}
	if (EditAccountInfomationPass2NewRe == null || EditAccountInfomationPass2NewRe == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng nhập lại mật khẩu mới.");return;
	}
	if (EditAccountInfomationPass2NewRe != EditAccountInfomationPass2New) {
		utils.MsgErrorEditAccountInfomation('Xác nhận mật khẩu mới không chính xác!');return;
	}
	if (EditAccountInfomationPass2CodeVerify.length != 4) {
		utils.MsgErrorEditAccountInfomation('Mã xác nhận không đúng!');return;
	}
	utils.WaitLoadingEditAccountInfo();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=editaccountinfosend_pass2&request=receiveddatacheckinfo",
		data: {
			UserNameRequest:$('#UserName4Request').val(),
			KeySend: "EditAccountInfoSend_Pass2",
			KeyRequestVerify: "EditAccountInfoSend_Pass2_jkjhKJHKJgy88hjhGH77gh",
			EditAccountInfomationPass2Old: EditAccountInfomationPass2Old,
			EditAccountInfomationPass2New: EditAccountInfomationPass2New,
			EditAccountInfomationPass2NewRe: EditAccountInfomationPass2NewRe,
			EditAccountInfomationPass2CodeVerify: EditAccountInfomationPass2CodeVerify
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingEditAccountInfoUnload();
			if(data.ReceivedDataOfEditAccountInfo4RequestAllData == 158542){
				$("#NotificationEditInfo").html("<a style='color:#1e6d0c;'>Đã cập nhật thông tin thành công!</a>");
				return AccountInfoAllDataEditInfo(2);
			}
			else{
				return utils.MsgErrorEditAccountInfomation(data.MsgError);
			}
		},
		error: function () {
			utils.WaitLoadingEditAccountInfoUnload();
			return utils.MsgErrorEditAccountInfomation("Các khai báo không hợp lệ! chỉ cho phép các ký tự từ a-z và 0-9.");
		}
	});
}

function btnSendInfoEditAccount2Server_QuestionAnwer(){
	var EditAccountInfomationQuestionOld = utils.convertUTFStr($('#EditAccountInfomationQuestionOld').val());
	var EditAccountInfomationAnswerOld = utils.convertUTFStr($('#EditAccountInfomationAnswerOld').val());
	var EditAccountInfomationQuestionNew = utils.convertUTFStr($('#EditAccountInfomationQuestionNew').val());
	var EditAccountInfomationAnswerNew = utils.convertUTFStr($('#EditAccountInfomationAnswerNew').val());
	var EditAccountInfomationQuestionAnswerCodeVerify = utils.convertUTFStr($('#EditAccountInfomationQuestionAnswerCodeVerify').val());

	if (EditAccountInfomationQuestionNew == null || EditAccountInfomationQuestionNew == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng chọn câu hỏi bảo mật mới.");return;
	}
	if (EditAccountInfomationAnswerNew == null || EditAccountInfomationAnswerNew == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng nhập câu trả lời bảo mật mới! yêu cầu 4-50 ký tự và a-z, 0-9.");return;
	}
	if (EditAccountInfomationAnswerNew.length < 4 || EditAccountInfomationAnswerNew.length > 50) {
		utils.MsgErrorEditAccountInfomation('Câu trả lời yêu cầu 4-50 ký tự và a-z, 0-9!');return;
	}
	if (EditAccountInfomationQuestionAnswerCodeVerify == null || EditAccountInfomationQuestionAnswerCodeVerify == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng nhập mã xác nhận.");return;
	}
	if (EditAccountInfomationQuestionAnswerCodeVerify.length != 4) {
		utils.MsgErrorEditAccountInfomation('Mã xác nhận không đúng!');return;
	}
	utils.WaitLoadingEditAccountInfo();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=editaccountinfosend_questionanwer&request=receiveddatacheckinfo",
		data: {
			UserNameRequest:$('#UserName4Request').val(),
			KeySend: "EditAccountInfoSend_QuestionAnswer",
			KeyRequestVerify: "EditAccountInfoSend_QuestionAnswer_jHuh8y0Jhh739hJH",
			EditAccountInfomationQuestionOld: EditAccountInfomationQuestionOld,
			EditAccountInfomationAnswerOld: EditAccountInfomationAnswerOld,
			EditAccountInfomationQuestionNew: EditAccountInfomationQuestionNew,
			EditAccountInfomationAnswerNew: EditAccountInfomationAnswerNew,
			EditAccountInfomationQuestionAnswerCodeVerify: EditAccountInfomationQuestionAnswerCodeVerify
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingEditAccountInfoUnload();
			if(data.ReceivedDataOfEditAccountInfo4RequestAllData == 158543){
				$("#NotificationEditInfo").html("<a style='color:#1e6d0c;'>Đã cập nhật thông tin thành công!</a>");
				return AccountInfoAllDataEditInfo(3);
			}
			else{
				return utils.MsgErrorEditAccountInfomation(data.MsgError);
			}
		},
		error: function () {
			utils.WaitLoadingEditAccountInfoUnload();
			return utils.MsgErrorEditAccountInfomation("Các khai báo không hợp lệ! chỉ cho phép các ký tự từ a-z và 0-9.");
		}
	});
}

function btnSendInfoEditAccount2Server_Email(){
	var EditInfoAccount_EmailOld = utils.convertUTFStrFormatEmail($('#EditInfoAccount_EmailOld').val());
	var EditInfoAccount_EmailNew = utils.convertUTFStrFormatEmail($('#EditInfoAccount_EmailNew').val());
	var EditInfoAccount_EmailNewRe = utils.convertUTFStrFormatEmail($('#EditInfoAccount_EmailNewRe').val());
	var EditInfoAccount_EmailCodeVerify = utils.convertUTFStr($('#EditInfoAccount_EmailCodeVerify').val());

	if (EditInfoAccount_EmailNew == null || EditInfoAccount_EmailNew == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng nhập địa chỉ Email mới.");return;
	}
	if (EditInfoAccount_EmailNew.length < 1 || EditInfoAccount_EmailNew.length > 50) {
		utils.MsgErrorEditAccountInfomation('Địa chỉ Email yêu cầu 1-50 ký tự và a-z, 0-9!');return;
	}
	if (EditInfoAccount_EmailNewRe == null || EditInfoAccount_EmailNewRe == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng xác nhận địa chỉ Email mới! yêu cầu 1-50 ký tự và a-z, 0-9.");return;
	}
	if (EditInfoAccount_EmailNewRe != EditInfoAccount_EmailNew) {
		utils.MsgErrorEditAccountInfomation('Xác nhận địa chỉ Email mới không đúng!');return;
	}
	if (EditInfoAccount_EmailCodeVerify == null || EditInfoAccount_EmailCodeVerify == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng nhập mã xác nhận.");return;
	}
	if (EditInfoAccount_EmailCodeVerify.length != 4) {
		utils.MsgErrorEditAccountInfomation('Mã xác nhận không đúng!');return;
	}
	utils.WaitLoadingEditAccountInfo();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=editaccountinfosend_email&request=receiveddatacheckinfo",
		data: {
			UserNameRequest:$('#UserName4Request').val(),
			KeySend: "EditAccountInfoSend_Email",
			KeyRequestVerify: "EditAccountInfoSend_Email_hyKJjhyuen7hjhe7jhHu",
			EditInfoAccount_EmailOld: EditInfoAccount_EmailOld,
			EditInfoAccount_EmailNew: EditInfoAccount_EmailNew,
			EditInfoAccount_EmailNewRe: EditInfoAccount_EmailNewRe,
			EditInfoAccount_EmailCodeVerify: EditInfoAccount_EmailCodeVerify
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingEditAccountInfoUnload();
			if(data.ReceivedDataOfEditAccountInfo4RequestAllData == 158544){
				$("#NotificationEditInfo").html("<a style='color:#1e6d0c;'>Đã cập nhật thông tin thành công!</a>");
				return AccountInfoAllDataEditInfo(4);
			}
			else{
				return utils.MsgErrorEditAccountInfomation(data.MsgError);
			}
		},
		error: function () {
			utils.WaitLoadingEditAccountInfoUnload();
			return utils.MsgErrorEditAccountInfomation("Các khai báo không hợp lệ! chỉ cho phép các ký tự từ a-z và 0-9.");
		}
	});
}

function btnSendInfoEditAccount2Server_InfoAcc(){
	var EditAccountInfoSend_FLNameUser = utils.convertUTFStr($('#EditAccountInfoSend_FLNameUser').val());
	var EditAccountInfoSend_PhoneNumber = utils.convertUTFStr($('#EditAccountInfoSend_PhoneNumber').val());
	var EditAccountInfoSend_InfoCodeVerify = utils.convertUTFStr($('#EditAccountInfoSend_InfoCodeVerify').val());

	if (EditAccountInfoSend_FLNameUser == null || EditAccountInfoSend_FLNameUser == "") {
		utils.MsgErrorEditAccountInfomation("Bạn vui lòng nhập Họ và Tên.");return;
	}
	if (EditAccountInfoSend_FLNameUser.length < 1 || EditAccountInfoSend_FLNameUser.length > 50) {
		utils.MsgErrorEditAccountInfomation('Tên người dùng yêu cầu 1-50 và ký tự a-z, 0-9!');return;
	}
	if (EditAccountInfoSend_PhoneNumber == null || EditAccountInfoSend_PhoneNumber == "") {
		utils.MsgErrorEditAccountInfomation("Số điện thoại không được để trống, cho phép ký tự 0-9.");return;
	}
	if (EditAccountInfoSend_PhoneNumber.length < 10 || EditAccountInfoSend_PhoneNumber.length > 12) {
		utils.MsgErrorEditAccountInfomation('Số điện thoại yêu cầu 10-12 ký tự 0-9!');return;
	}
	if (EditAccountInfoSend_InfoCodeVerify == null || EditAccountInfoSend_InfoCodeVerify == "") {
		utils.MsgErrorEditAccountInfomation("Bạn chưa nhập mã xác nhận.");return;
	}
	if (EditAccountInfoSend_InfoCodeVerify.length != 4) {
		utils.MsgErrorEditAccountInfomation('Mã xác nhận không đúng!');return;
	}
	utils.WaitLoadingEditAccountInfo();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=editaccountinfosend_infoacc&request=receiveddatacheckinfo",
		data: {
			UserNameRequest:$('#UserName4Request').val(),
			KeySend: "EditAccountInfoSend_InfoAcc",
			KeyRequestVerify: "EditAccountInfoSend_InfoAcc_jhhjHHhuhel887jHhyeh68",
			EditAccountInfoSend_FLNameUser: EditAccountInfoSend_FLNameUser,
			EditAccountInfoSend_PhoneNumber: EditAccountInfoSend_PhoneNumber,
			EditAccountInfoSend_InfoCodeVerify: EditAccountInfoSend_InfoCodeVerify
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingEditAccountInfoUnload();
			if(data.ReceivedDataOfEditAccountInfo4RequestAllData == 158545){
				$("#NotificationEditInfo").html("<a style='color:#1e6d0c;'>Đã cập nhật thông tin thành công!</a>");
				return AccountInfoAllDataEditInfo(5);
			}
			else{
				return utils.MsgErrorEditAccountInfomation(data.MsgError);
			}
		},
		error: function () {
			utils.WaitLoadingEditAccountInfoUnload();
			return utils.MsgErrorEditAccountInfomation("Các khai báo không hợp lệ! chỉ cho phép các ký tự từ a-z và 0-9.");
		}
	});
}

function IFogetPassword(){
	utils.WaitLoading();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=iforgetpassword&request=receiveddatacheckinforequestpwd",
		data: {
			KeySend: "iForgetPassword",
			KeyRequestVerify: "iForgetPassword_kjUHjr899jJhje7KJ7k",
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingUnload();
			if(data.ReceivedDataOfForgetPasswordRequestData == 879654){
				$("#OpenPopupForgetPwd").remove();
				$("body").append(data.ReceivedDataOfForgetPasswordRequestAllData);
				return IFogetPassword_UsedPass2aQA(1);
			}
			else{
				return utils.ErrorMessage(data.MsgError);
			}
		},
		error: function () {
			utils.WaitLoadingUnload();
			return utils.ErrorMessage("Hệ thống đang bận, bạn vui lòng thử lại sau!");
		}
	});
}

function ClosePopupForgetPwd(){
	return $("#OpenPopupForgetPwd").remove();
}

function IFogetPassword_UsedPass2aQA(Sel){
	if(Sel == 1){
		var content = "usedpass2";
		ReceivedDataOfForgetPasswordRequestPass2 = 879655;
		$("#btnForgetPassUsedPass2").css({"background-color": "#1b89b1", "color": "#fff"});
		$("#btnForgetPassUsedQA").css({"background-color": "#929292", "color": "#000"});
	}
	else{
		if(Sel == 2){
			var content = "usedquestionanswer";
			ReceivedDataOfForgetPasswordRequestPass2 = 879656;
			$("#btnForgetPassUsedPass2").css({"background-color": "#929292", "color": "#000"});
			$("#btnForgetPassUsedQA").css({"background-color": "#1b89b1", "color": "#fff"});
		}
	}
	$("#ForgetPwdContent").empty();
	$("#ForgetPwdContent").html("<img src='/include/web_skins/default/images/loading.gif' style='margin-top: 81px;border-radius: 12px;'></img>");
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=iforgetpassword&request=receiveddatacheckinforequestpwd&content=" + content,
		data: {
			KeySend: "iForgetPassword",
			KeyRequestVerify: "iForgetPassword_kjUHjr899jJhje7KJ7k",
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingUnload();
			if(data.ReceivedDataOfForgetPasswordRequestPass2 == ReceivedDataOfForgetPasswordRequestPass2){
				$("#ForgetPwdContent").empty();
				$("#ForgetPwdContent").append(data.ReceivedDataOfForgetPasswordRequestPass2AllData);
				return;
			}
			else{
				return ClosePopupForgetPwd();
			}
		},
		error: function () {
			$("#ForgetPwdContent").empty();
			return ClosePopupForgetPwd();
		}
	});
}

function IFogetPasswordUsedPass2aQASendData2ServerPass2(){
	var iforgetpasswordUsedPass2_Account = utils.convertUTFStr($('#iforgetpasswordUsedPass2_Account').val());
	var iforgetpasswordUsedPass2_Pass2Old = utils.convertUTFStr($('#iforgetpasswordUsedPass2_Pass2Old').val());
	var iforgetpasswordUsedPass2_Pass1New = utils.convertUTFStr($('#iforgetpasswordUsedPass2_Pass1New').val());
	var iforgetpasswordUsedPass2_Pass1NewRe = utils.convertUTFStr($('#iforgetpasswordUsedPass2_Pass1NewRe').val());
	var iforgetpasswordUsedPass2_CodeVerify = utils.convertUTFStr($('#iforgetpasswordUsedPass2_CodeVerify').val());
	if (iforgetpasswordUsedPass2_Account == null || iforgetpasswordUsedPass2_Account == "") {
		utils.MsgErrorForgetPassword("Bạn vui lòng nhập tên tài khoản");
		return;
	}
	if (iforgetpasswordUsedPass2_Account.length < 4 || iforgetpasswordUsedPass2_Account.length > 24) {
		utils.MsgErrorForgetPassword('Tên tài khoản từ 4-24 ký tự');
		return;
	}
	if (iforgetpasswordUsedPass2_Pass2Old == null || iforgetpasswordUsedPass2_Pass2Old == "") {
		utils.MsgErrorForgetPassword("Bạn chưa nhập mã cấp 2");
		return;
	}
	if (iforgetpasswordUsedPass2_Pass1New == null || iforgetpasswordUsedPass2_Pass1New == "") {
		utils.MsgErrorForgetPassword("Bạn chưa nhập mật khẩu mới");
		return;
	}
	if (iforgetpasswordUsedPass2_Pass1New.length < 4 || iforgetpasswordUsedPass2_Pass1New.length > 24) {
		utils.MsgErrorForgetPassword('Mật khẩu cho phép từ 4-24 ký tự');
		return;
	}
	if (iforgetpasswordUsedPass2_Pass1NewRe == null || iforgetpasswordUsedPass2_Pass1NewRe == "") {
		utils.MsgErrorForgetPassword("Bạn chưa nhập lại mật khẩu mới");
		return;
	}
	if (iforgetpasswordUsedPass2_Pass1NewRe != iforgetpasswordUsedPass2_Pass1New) {
		utils.MsgErrorForgetPassword("Mật khẩu mới và xác nhận mật khẩu không giống nhau");
		return;
	}
	if (iforgetpasswordUsedPass2_CodeVerify == null || iforgetpasswordUsedPass2_CodeVerify == "") {
		utils.MsgErrorForgetPassword("Bạn chưa nhập mã xác nhận");
		return;
	}
	if (iforgetpasswordUsedPass2_CodeVerify.length != 4) {
		utils.MsgErrorForgetPassword('Mã xác nhận không đúng');
		return;
	}
	utils.WaitLoadingForgetPasswd();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=iforgetpasswordsend2server&request=checkinfopass2password",
		data: {
			KeySend: "iForgetPasswordSend2ServerPass2",
			KeyRequestVerify: "iForgetPasswordSend2ServerPass2_kjUHjr899jJhje7KJ7kp2",
			iforgetpasswordUsedPass2_Account: iforgetpasswordUsedPass2_Account,
			iforgetpasswordUsedPass2_Pass2Old: iforgetpasswordUsedPass2_Pass2Old,
			iforgetpasswordUsedPass2_Pass1New: iforgetpasswordUsedPass2_Pass1New,
			iforgetpasswordUsedPass2_Pass1NewRe: iforgetpasswordUsedPass2_Pass1NewRe,
			iforgetpasswordUsedPass2_CodeVerify: iforgetpasswordUsedPass2_CodeVerify
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingForgetPasswdUnload();
			if(data.ReceivedDataOfForgetPasswordRequestPass2Fsv == 879657){
				$("#ForgetPwdContent").empty();
				$("#ForgetPwdContent").append(data.ReceivedDataOfForgetPasswordRequestPass2FsvAllData);
				return;
			}
			else{
				return utils.MsgErrorForgetPassword(data.MsgError);
			}
		},
		error: function () {
			$("#ForgetPwdContent").empty();
			return utils.MsgErrorForgetPassword("Các khai báo không hợp lệ, cho phép ký tự a-z,0-9!");
		}
	});
}

function IFogetPasswordUsedPass2aQASendData2ServerQA(){
	var iforgetpasswordUsedQA_Account = utils.convertUTFStr($('#iforgetpasswordUsedQA_Account').val());
	var iforgetpasswordUsedQA_QuestionOld = utils.convertUTFStr($('#iforgetpasswordUsedQA_QuestionOld').val());
	var iforgetpasswordUsedQA_AnswerOld = utils.convertUTFStr($('#iforgetpasswordUsedQA_AnswerOld').val());
	var iforgetpasswordUsedQA_Pass1New = utils.convertUTFStr($('#iforgetpasswordUsedQA_Pass1New').val());
	var iforgetpasswordUsedQA_Pass1NewRe = utils.convertUTFStr($('#iforgetpasswordUsedQA_Pass1NewRe').val());
	var iforgetpasswordUsedQA_CodeVerify = utils.convertUTFStr($('#iforgetpasswordUsedQA_CodeVerify').val());
	if (iforgetpasswordUsedQA_Account == null || iforgetpasswordUsedQA_Account == "") {
		utils.MsgErrorForgetPassword("Bạn vui lòng nhập tên tài khoản");
		return;
	}
	if (iforgetpasswordUsedQA_Account.length < 4 || iforgetpasswordUsedQA_Account.length > 24) {
		utils.MsgErrorForgetPassword('Tên tài khoản từ 4-24 ký tự');
		return;
	}
	if (iforgetpasswordUsedQA_AnswerOld == null || iforgetpasswordUsedQA_AnswerOld == "") {
		utils.MsgErrorForgetPassword("Bạn chưa nhập câu trả lời bảo mật");
		return;
	}
	if (iforgetpasswordUsedQA_AnswerOld.length < 4 || iforgetpasswordUsedQA_AnswerOld.length > 50) {
		utils.MsgErrorForgetPassword('Câu trả lời từ 4-50 ký tự');
		return;
	}
	if (iforgetpasswordUsedQA_Pass1New == null || iforgetpasswordUsedQA_Pass1New == "") {
		utils.MsgErrorForgetPassword("Bạn chưa nhập mật khẩu mới");
		return;
	}
	if (iforgetpasswordUsedQA_Pass1New.length < 4 || iforgetpasswordUsedQA_Pass1New.length > 24) {
		utils.MsgErrorForgetPassword('Mật khẩu từ 4-24 ký tự');
		return;
	}
	if (iforgetpasswordUsedQA_Pass1NewRe == null || iforgetpasswordUsedQA_Pass1NewRe == "") {
		utils.MsgErrorForgetPassword("Bạn chưa nhập lại mật khẩu mới");
		return;
	}
	if (iforgetpasswordUsedQA_Pass1NewRe != iforgetpasswordUsedQA_Pass1New) {
		utils.MsgErrorForgetPassword('Mật khẩu mới và xác nhận mật khẩu mới không đúng');
		return;
	}
	if (iforgetpasswordUsedQA_CodeVerify == null || iforgetpasswordUsedQA_CodeVerify == "") {
		utils.MsgErrorForgetPassword("Bạn chưa nhập mã bảo mật");
		return;
	}
	if (iforgetpasswordUsedQA_CodeVerify.length != 4) {
		utils.MsgErrorForgetPassword('Mã xác nhận không đúng');
		return;
	}
	utils.WaitLoadingForgetPasswd();
	$.ajax({
		type: "POST",
		cache: false,
		url: bil_gSkin+"skin_account.php?action=iforgetpasswordsend2server&request=checkinfopass2questionanswer",
		data: {
			KeySend: "iForgetPasswordSend2ServerQuestionAnswer",
			KeyRequestVerify: "iForgetPasswordSend2ServerQuestionAnswer_jJHH889kjgy7G",
			iforgetpasswordUsedQA_Account: iforgetpasswordUsedQA_Account,
			iforgetpasswordUsedQA_QuestionOld: iforgetpasswordUsedQA_QuestionOld,
			iforgetpasswordUsedQA_AnswerOld: iforgetpasswordUsedQA_AnswerOld,
			iforgetpasswordUsedQA_Pass1New: iforgetpasswordUsedQA_Pass1New,
			iforgetpasswordUsedQA_Pass1NewRe: iforgetpasswordUsedQA_Pass1NewRe,
			iforgetpasswordUsedQA_CodeVerify: iforgetpasswordUsedQA_CodeVerify
		},
		dataType: "json",
		success: function (data) {
			utils.WaitLoadingForgetPasswdUnload();
			if(data.ReceivedDataOfForgetPasswordRequestQAFsv == 879658){
				$("#ForgetPwdContent").empty();
				$("#ForgetPwdContent").append(data.ReceivedDataOfForgetPasswordRequestQAFsvAllData);
				return;
			}
			else{
				return utils.MsgErrorForgetPassword(data.MsgError);
			}
		},
		error: function () {
			$("#ForgetPwdContent").empty();
			return utils.MsgErrorForgetPassword("Các khai báo không hợp lệ, cho phép ký tự a-z,0-9!");
		}
	});
}

function iDontKnow(){
	return utils.ErrorMessagePopup('Tính năng này chưa được cập nhật, khi nào cập nhật sẽ có thông báo sau. Thân!');
}

function CauhoiNapTheGame(Sel){
	if(Sel==1){
		var MsgRt = 'Bạn chuyển qua tab nạp thẻ, sau đó chọn loại thẻ cần nạp, điền đầy đủ các thông tin và nhấn vào nạp thẻ, đợi kết quả trả về từ máy chủ.';
	}
	if(Sel==2){
		var MsgRt = 'Sau khi nạp thẻ thành công bạn cần thoát game sau đó đăng nhập lại và đến gặp Tiền trang ở thất đại thành thị để kiểm tra tiền đồng.';
	}
	if(Sel==3){
		var MsgRt = 'Tiền đồng chỉ có thể dùng để mua các vật phẩm trong Kỳ trân các, không thể giao dịch, các vật phẩm mua bằng tiền đồng sẽ không bị khóa.';
	}
	return utils.ErrorMessagePopup(MsgRt);
}

window.utils = {
	ErrorMessage: function(text){
	        this.clearErrorMessage("lblError");
        var html =text;
        $('#lblError').html(html);
    },
	ErrorMessageRegisterPopupAjax: function(text){
	        this.clearErrorMessage("RegisterPopupAjaxSentError");
        var html =text;
        $('#RegisterPopupAjaxSentError').html(html);
    },
	    clearErrorMessage: function (fieldid) {
        $('#' + fieldid).empty();
    },
    convertUTFStr: function (str) {
        // str = str.toLowerCase();
        str = str.replace(/à|á|ạ|ả|ã|â|ầ|ấ|ậ|ẩ|ẫ|ă|ằ|ắ|ặ|ẳ|ẵ/g, "a");
        str = str.replace(/À|Á|Ạ|Ả|Ã|Â|Ầ|Ấ|Ậ|Ẩ|Ẫ|Ă|Ằ|Ắ|Ặ|Ẳ|Ẵ/g, "A");
        str = str.replace(/è|é|ẹ|ẻ|ẽ|ê|ề|ế|ệ|ể|ễ/g, "e");
        str = str.replace(/È|É|Ẹ|Ẻ|Ẽ|Ê|Ề|Ế|Ệ|Ể|Ễ/g, "E");
        str = str.replace(/ì|í|ị|ỉ|ĩ/g, "i");
        str = str.replace(/Ì|Í|Ị|Ỉ|Ĩ/g, "I");
        str = str.replace(/ò|ó|ọ|ỏ|õ|ô|ồ|ố|ộ|ổ|ỗ|ơ|ờ|ớ|ợ|ở|ỡ/g, "o");
        str = str.replace(/Ò|Ó|Ọ|Ỏ|Õ|Ô|Ồ|Ố|Ộ|Ổ|Ỗ|Ơ|Ờ|Ớ|Ợ|Ở|Ỡ/g, "O");
        str = str.replace(/ù|ú|ụ|ủ|ũ|ư|ừ|ứ|ự|ử|ữ/g, "u");
        str = str.replace(/Ù|Ú|Ụ|Ủ|Ũ|Ư|Ừ|Ứ|Ự|Ử|Ữ/g, "U");
        str = str.replace(/ỳ|ý|ỵ|ỷ|ỹ/g, "y");
        str = str.replace(/Ỳ|Ý|Ỵ|Ỷ|Ỹ/g, "Y");
        str = str.replace(/đ/g, "d");
        str = str.replace(/Đ/g, "D");
        str = str.replace(/!|@|%|\^|\*|\(|\)|\+|\=|\<|\>|\?|\/|,|\.|\:|\;|\'| |\"|\&|\#|\[|\]|~|$|_/g, "-");
        str = str.replace(/-+-/g, "-");
        str = str.replace(/^\-+|\-+$/g, "");
        return str;
    }, 
    convertUTFStrFormatEmail: function (str) {
        str = str.toLowerCase();
        str = str.replace(/à|á|ạ|ả|ã|â|ầ|ấ|ậ|ẩ|ẫ|ă|ằ|ắ|ặ|ẳ|ẵ/g, "a");
        str = str.replace(/è|é|ẹ|ẻ|ẽ|ê|ề|ế|ệ|ể|ễ/g, "e");
        str = str.replace(/ì|í|ị|ỉ|ĩ/g, "i");
        str = str.replace(/ò|ó|ọ|ỏ|õ|ô|ồ|ố|ộ|ổ|ỗ|ơ|ờ|ớ|ợ|ở|ỡ/g, "o");
        str = str.replace(/ù|ú|ụ|ủ|ũ|ư|ừ|ứ|ự|ử|ữ/g, "u");
        str = str.replace(/ỳ|ý|ỵ|ỷ|ỹ/g, "y");
        str = str.replace(/đ/g, "d");
        str = str.replace(/!|%|\^|\*|\(|\)|\+|\=|\<|\>|\?|\/|,|\:|\;|\'| |\"|\&|\#|\[|\]|~|$/g, "-");
        str = str.replace(/-+-/g, "-");
        str = str.replace(/^\-+|\-+$/g, "");
        return str;
    }, 
	WaitLoading: function(){
		this.WaitLoadingUnload();
		$("body").append("<div id='WaitLoading'><img src='/include/web_skins/default/images/loading.gif'></img></div>");
	},
	WaitLoadingUnload: function(){
		$("#WaitLoading").remove();
	},
	WaitLoadingAccountInfo: function(){
		this.WaitLoadingAccountInfoUnLoad();
		$(".Acc_Frame").append("<div id='WaitLoadingAccountInfo' class='WaitLoadingAccountInfo'><img src='/include/web_skins/default/images/loading.gif'></img></div>");
	},
	WaitLoadingAccountInfoUnLoad: function(){
		$("#WaitLoadingAccountInfo").remove();
	},
	WaitLoadingCheckCardInfo: function(){
		this.WaitLoadingCheckCardInfoUnload();
		$("body").append("<div id='WaitLoadingCheckCardInfo' style='background: rgba(0, 0, 0, 0.6);position: fixed;text-align: center;width: 100%;height: 100%;top: 0;padding-top:20%;font-size:12px;color:#fff;'><img src='/include/web_skins/default/images/loading.gif' style='border-radius:12px;'></img><br><a style='color:#fff'>Đang kiểm tra thẻ nạp, phiền bạn vui lòng đợi giây lát!<br>Bạn đừng tắt trình duyệt khi chưa kiểm tra xong.</a></div>")
	},
	WaitLoadingCheckCardInfoUnload: function(){
		$("#WaitLoadingCheckCardInfo").remove();
	},
	MsgErrorNapTheTienDong: function(text){
	        this.clearErrorMessage("MsgErrorNapThe");
        var html =text;
        $('#MsgErrorNapThe').html(html);
    },
	MsgErrorForgetPassword: function(text){
	        this.clearErrorMessage("ForgetPwdNotifyCError");
        var html =text;
        $('#ForgetPwdNotifyCError').html(html);
    },
	WaitLoadingEditInfo: function(){
		this.WaitLoadingCheckCardInfoUnload();
		$("#FormEditInfoAccount").append("<div id='WaitLoadingEditInfo'style='text-align: center;height:305px;'><img src='/include/web_skins/default/images/loading.gif' style='margin-top: 86px;border-radius:12px;'></img></div>")
	},
	WaitLoadingEditInfoUnload: function(){
		$("#WaitLoadingEditInfo").remove();
	},
	MsgErrorEditAccountInfomation: function(text){
	        this.clearErrorMessage("NotificationEditInfo");
        var html =text;
        $('#NotificationEditInfo').html(html);
    },
	WaitLoadingEditAccountInfo: function(){
		this.WaitLoadingEditAccountInfoUnload();
		$("body").append("<div id='WaitLoadingEditAccountInfo' style='background: rgba(0, 0, 0, 0.6);position: fixed;text-align: center;width: 100%;height: 100%;top: 0;padding-top:20%;font-size:12px;color:#fff;'><img src='/include/web_skins/default/images/loading.gif' style='border-radius:12px;'></img><br><a style='color:#fff'>Vui lòng đợi giây lát, đang cập nhật thông tin...</a></div>");
	},
	WaitLoadingEditAccountInfoUnload: function(){
		$("#WaitLoadingEditAccountInfo").remove();
	},
	WaitLoadingForgetPasswd: function(){
		this.WaitLoadingForgetPasswdUnload();
		$("#OpenPopupForgetPwd").append("<div id='WaitLoadingForgetPasswd' style='background: rgba(0, 0, 0, 0.6);position: fixed;text-align: center;width: 100%;height: 100%;top: 0;padding-top:20%;font-size:12px;color:#fff;'><img src='/include/web_skins/default/images/loading.gif'></img><br><a style='color:#fff;'>Vui lòng đợi giây lát, đang kiểm tra thông tin...</a></div>");
	},
	WaitLoadingForgetPasswdUnload: function(){
		$("#WaitLoadingForgetPasswd").remove();
	},
	ErrorMessagePopup :function(text){
		this.ErrorMessagePopupUn();
		$('body').append('<div id=ErrorMessagePopup style=position:fixed;top:0;width:100%;text-align:center;height:100%;background:rgba(0,0,0,0.68);z-index:99999;><div style=margin:auto;padding-top:12px;padding-bottom:12px;background:rgba(255,255,255,0.23);border-radius:8px;color:#11AF00;margin-top:18%;font-size:14px;><a style=color:#fff;>' + text + '</a><br><input style=text-align:center;outline:0;background:#fd7727;border:none;color:#fff;height:29px;width:79px;border-radius:4px;padding-left:8px;margin-top:9px;cursor:pointer; type="submit" value=OK onclick=utils.ErrorMessagePopupUn()></div></div>');
	},
	ErrorMessagePopupUn: function(){
		$('#ErrorMessagePopup').remove();
	},
	ErrorMessagePopupToken :function(text){
		this.ErrorMessagePopupUn();
		$('body').append('<div style=position:fixed;top:0;width:100%;text-align:center;height:100%;background:rgba(0,0,0,0.68);z-index:99999;><div style=margin:auto;padding-top:12px;padding-bottom:12px;background:#fff;border-radius:8px;color:#11AF00;margin-top:18%;font-size:14px;><a>' + text + '</a><br><input style=text-align:center;outline:0;background:#00224C;border:none;color:#fff;height:29px;width:79px;border-radius:4px;padding-left:8px;margin-top:9px;cursor:pointer; type="submit" value=OK onclick=utils.ErrorMessagePopupTokenUn()></div></div>');
	},
	ErrorMessagePopupTokenUn: function(){
		$('body').append("<META HTTP-EQUIV='refresh' CONTENT='0; URL=../skin_index.php'>");
	},
};
/*   developer: bil4i3n, contact:: fb.com/bil.jx   */