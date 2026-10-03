(() => {
  'use strict';
  const root = document.getElementById('storage-app');
  if (!root) return;
  const $ = id => document.getElementById('s-' + id);
  const state = {data:null, group:'all', version:'all', selected:new Set(), source:null,
    files:new Set(), filePage:1, filePages:1, visibleFiles:[], preview:null, previewPage:1,
    previewPages:1, showSkipped:false, deleteSources:[], deleteFiles:null, previewSeq:0, detailsSeq:0, busy:false};
  const fmt = value => {let n = Number(value)||0, unit=0; const units=['B','KB','MB','GB','TB']; while(Math.abs(n)>=1024 && unit<4){n/=1024;unit++;} return n.toLocaleString('vi-VN',{maximumFractionDigits:unit?1:0})+' '+units[unit];};
  const date = value => value ? new Date(value*1000).toLocaleString('vi-VN') : '—';
  const node = (tag, text, cls) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const button = (text, action, cls='mut') => {const b=node('button',text,cls);b.type='button';b.addEventListener('click',action);return b;};
  const canClean = source => !['protected','docker'].includes(source.mode);
  const canSelect = source => canClean(source) && source.mode!=='journal' && source.files>0;
  async function api(path, data) {
    const response=await fetch(root.dataset.api+'/'+path, {method:data===undefined?'GET':'POST',
      headers:{Accept:'application/json',...(data===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':root.dataset.csrf})},
      body:data===undefined?undefined:JSON.stringify(data),cache:'no-store'});
    if(response.redirected)throw new Error('Phiên đăng nhập đã hết hạn; vui lòng tải lại trang.');
    let result;try{result=await response.json();}catch(e){throw new Error('Máy chủ chưa trả kết quả hợp lệ; hãy thử lại.');}
    if(!response.ok)throw new Error(result.error||'Không hoàn tất thao tác');return result;
  }
  const status = (message,error=false) => {$('status').textContent=message;$('status').classList.toggle('s-error',error);};
  function fillOptions(select, items, selected) {select.replaceChildren();for(const item of items){const option=node('option',item.label);option.value=item.id;select.append(option);}select.value=selected;}
  async function scan(force=false) {
    $('refresh').disabled=true;$('quick-clean').disabled=true;status('Đang quét log và dump…');
    try {state.data=await api(force?'scan':'snapshot',force?{}:undefined);
      state.data.sources=state.data.cleanup.sources;state.data.groups=state.data.cleanup.groups;
      fillOptions($('version'),[{id:'all',label:'Tất cả phiên bản'},{id:'active',label:'Server đang dùng'},...state.data.versions.map(v=>({id:v.name,label:v.name+(v.active?' · đang dùng':'')}))],state.version);
      fillOptions($('group'),[{id:'all',label:'Tất cả nhóm'},...state.data.groups],state.group);
      state.selected.clear();render();
      const errors=state.data.sources.reduce((sum,s)=>sum+s.errors,0);
      status(errors?'Có '+errors+' lỗi đọc; hãy kiểm tra chi tiết.':'Lần quét: '+date(state.data.scanned_at),!!errors);
      $('quick-clean').disabled=!state.data.sources.some(s=>canClean(s)&&s.files>0);
    } catch(e){status(e.message,true);}finally{$('refresh').disabled=false;}
  }
  function renderSummary() {
    for(const group of state.data.groups){
      $(group.id+'-total').textContent=fmt(group.allocated);
      $(group.id+'-files').textContent=group.files.toLocaleString('vi-VN')+' file'+(group.memory_allocated?' · '+fmt(group.memory_allocated)+' RAM riêng':' · Xem chi tiết');
    }
    const unknown=state.data.cleanup.unknown_dumps;
    $('unknown-dumps').hidden=!unknown;
    $('unknown-dumps').textContent=unknown+' file crash khác hoặc chưa xác định nguồn vẫn được hiển thị; Dọn nhanh giữ lại các file này.';
  }
  function sourcesForView() {
    const q=$('search').value.trim().toLocaleLowerCase();
    const version=state.version==='active'?state.data.versions.find(v=>v.active)?.name:state.version;
    return state.data.sources.filter(s=>(state.group==='all'||s.group===state.group) &&
      (!s.version||state.version==='all'||s.version===version) && (s.label+' '+s.path+' '+s.version).toLocaleLowerCase().includes(q));
  }
  function selection() {
    $('selected').textContent=state.selected.size?state.selected.size+' nguồn đã chọn · sẽ xem trước trước khi xóa':'Chưa chọn nguồn để dọn';
    $('clear-selection').hidden=!state.selected.size;$('bulk-delete').disabled=!state.selected.size;
  }
  function renderGroups() {
    if(!state.data)return;
    const sources=sourcesForView();$('groups').replaceChildren();
    for(const group of state.data.groups){const rows=sources.filter(s=>s.group===group.id).sort((a,b)=>b.allocated-a.allocated);if(!rows.length)continue;
      const card=node('section',undefined,'s-group-card'),head=node('div',undefined,'s-group-head');
      const dot=node('span',undefined,'s-dot');dot.style.background=group.color;
      head.append(dot,node('h3',group.label),node('strong',fmt(rows.reduce((n,s)=>n+(s.memory?0:s.allocated),0))+(rows.some(s=>s.memory)?' trên ổ · '+fmt(rows.filter(s=>s.memory).reduce((n,s)=>n+s.allocated,0))+' RAM':'')));card.append(head);
      for(const source of rows){const row=node('div',undefined,'s-source');
        const slot=node('div');if(canSelect(source)){const check=document.createElement('input');check.type='checkbox';check.checked=state.selected.has(source.id);check.setAttribute('aria-label','Chọn '+source.label+' '+source.version);check.addEventListener('change',()=>{check.checked?state.selected.add(source.id):state.selected.delete(source.id);selection();});slot.append(check);}row.append(slot);
        const content=node('div'),title=node('div',undefined,'s-source-title');title.append(node('b',source.label));
        if(source.version){const active=state.data.versions.find(v=>v.name===source.version)?.active;title.append(node('span',source.version+(active?' · đang dùng':''),'s-tag'+(active?' s-active':'')));}
        if(source.memory)title.append(node('span','Trong RAM','s-tag'));
        if(!canClean(source))title.append(node('span',source.mode==='docker'?'Tự xoay vòng':'Chỉ theo dõi','s-tag'));
        content.append(title,node('code',source.path));
        const info=source.errors?'Có lỗi đọc · '+source.errors:!source.exists?'Thư mục chưa tồn tại':!source.files?'Trống · đã kiểm tra':source.note||('Cập nhật: '+date(source.latest));content.append(node('p',info,'s-source-note'));row.append(content);
        const size=node('div',undefined,'s-source-size');size.append(node('b',fmt(source.allocated)),node('small',source.files.toLocaleString('vi-VN')+' file'),node('small',source.memory?'Trong RAM':'Nội dung '+fmt(source.bytes)));row.append(size);
        const actions=node('div',undefined,'s-source-actions');actions.append(button('Chi tiết',()=>openDetails(source)));
        if(canClean(source)){const del=button('Dọn',()=>openDelete([source.id]),'err');del.disabled=!source.files;actions.append(del);}else if(source.group==='backup'&&source.label==='Backup database'){actions.append(button('Quản lý',()=>location.assign(root.dataset.backups)));}
        if(source.custom_relative)actions.append(button('Bỏ theo dõi',async()=>{
          const message='Bỏ đường dẫn này khỏi danh sách theo dõi của các phiên bản? File và thư mục được giữ nguyên.';
          const approved=window.JXDialog?await window.JXDialog.confirm(message):window.confirm(message);if(!approved)return;
          const form=document.createElement('form');form.method='POST';form.action=root.dataset.remove;
          for(const [name,value] of Object.entries({csrf_token:root.dataset.csrf,path:source.custom_relative})){const input=document.createElement('input');input.type='hidden';input.name=name;input.value=value;form.append(input);}document.body.append(form);form.submit();
        }));
        row.append(actions);card.append(row);
      }$('groups').append(card);
    }
    if(!sources.length)$('groups').append(node('div','Không có nguồn phù hợp với bộ lọc.','s-empty'));
    selection();
  }
  function render(){renderSummary();renderGroups();}
  function closeDialog(dialog){if(state.busy)return;dialog.close();if(dialog===$('delete-dialog')){state.previewSeq++;state.preview=null;$('confirm-delete').disabled=true;}}
  document.querySelectorAll('.s-dialog').forEach(dialog=>{dialog.querySelectorAll('[data-s-close]').forEach(b=>b.addEventListener('click',()=>closeDialog(dialog)));dialog.addEventListener('cancel',event=>{event.preventDefault();closeDialog(dialog);});dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeDialog(dialog);});});
  async function openDetails(source){state.source=source;state.files.clear();state.filePage=1;$('file-search').value='';$('file-sort').value='size';$('detail-title').textContent=source.label+(source.version?' · '+source.version:'');$('detail-path').textContent=source.path;$('detail-info').textContent=source.files+' file · '+fmt(source.bytes)+' nội dung · '+fmt(source.allocated)+(source.memory?' trong RAM':' trên ổ');$('detail-note').textContent=source.note||'File đang mở hoặc vừa thay đổi được bỏ qua khi dọn.';$('backup-link').hidden=source.label!=='Backup database';$('delete-source').hidden=!canClean(source);$('delete-source').disabled=!source.files;$('delete-files').hidden=!canSelect(source);$('select-page').closest('label').hidden=!canSelect(source);$('detail-dialog').showModal();await loadFiles();}
  function fileRow(file, check=false){const row=node('div',undefined,'s-file');if(check){const c=document.createElement('input');c.type='checkbox';c.checked=state.files.has(file.id);c.setAttribute('aria-label','Chọn '+file.name);c.addEventListener('change',()=>{c.checked?state.files.add(file.id):state.files.delete(file.id);fileSelection();});row.append(c);}const main=node('div',undefined,'s-file-main');main.append(node('div',file.name,'s-file-name'),node('div',file.path,'s-file-path'),node('div',date(file.mtime)+(file.version?' · Phiên bản '+file.version:'')+(file.process?' · '+file.process:'')+(file.reason?' · '+file.reason:''),'s-file-meta'));row.append(main,node('span',fmt(file.bytes),'s-file-size'));return row;}
  function fileSelection(){$('delete-files').disabled=!state.files.size;$('file-selection').textContent=state.files.size?state.files.size+' file đã chọn':'';$('select-page').checked=!!state.visibleFiles.length&&state.visibleFiles.every(f=>state.files.has(f.id));$('select-page').indeterminate=state.visibleFiles.some(f=>state.files.has(f.id))&&!$('select-page').checked;}
  async function loadFiles(){const seq=++state.detailsSeq;$('files').replaceChildren(node('div','Đang tải danh sách file…','s-empty'));try{const query=new URLSearchParams({source:state.source.id,page:state.filePage,sort:$('file-sort').value,q:$('file-search').value,scope:'quick'});const data=await api('details?'+query);if(seq!==state.detailsSeq)return;state.filePage=data.page;state.filePages=data.pages;state.visibleFiles=data.files;$('files').replaceChildren(...data.files.map(f=>fileRow(f,canSelect(state.source))));if(!data.files.length)$('files').append(node('div','Không có file phù hợp.','s-empty'));$('file-page').textContent='Trang '+data.page+' / '+data.pages+' · '+data.total+' file';$('file-prev').disabled=data.page<=1;$('file-next').disabled=data.page>=data.pages;fileSelection();}catch(e){if(seq===state.detailsSeq)$('files').replaceChildren(node('div',e.message,'s-empty'));}}
  async function openDelete(sources=null, files=null){
    state.deleteSources=sources;state.deleteFiles=files;state.preview=null;state.showSkipped=false;state.previewPage=1;
    $('delete-title').textContent=sources===null?'Dọn nhanh':'Dọn dữ liệu đã chọn';
    $('preview-expanded').open=false;
    $('delete-sources').replaceChildren();
    if(sources===null){
      $('delete-sources').append(node('div','Log server · Dump / crash · QuanLy One · Log dịch vụ'),node('small','Mọi phiên bản; Nginx đã xoay và journal lưu trữ. Docker tự xoay log.'));
    }else if(sources.length===1){
      const source=state.data.sources.find(s=>s.id===sources[0]);
      $('delete-sources').append(node('div',source.label+(source.version?' · '+source.version:'')),node('code',source.path));
    }else $('delete-sources').append(node('div',sources.length+' nguồn log / dump đã chọn'));
    if(files)$('delete-sources').append(node('b','Phạm vi: '+files.length+' file đã chọn'));
    document.querySelector('input[name="s-days"][value="7"]').checked=true;
    $('delete-dialog').showModal();await preview();
  }
  async function preview(){const seq=++state.previewSeq;state.preview=null;state.previewPage=1;state.showSkipped=false;$('confirm-delete').disabled=true;$('preview-status').textContent='Đang kiểm tra file và lập danh sách xem trước…';$('preview-metrics').replaceChildren();$('preview-files').replaceChildren();$('preview-page').textContent='';$('journal-note').hidden=true;try{const days=document.querySelector('input[name="s-days"]:checked').value;const data=await api('preview',{scope:'quick',sources:state.deleteSources,days,...(state.deleteFiles?{files:state.deleteFiles}:{})});if(seq!==state.previewSeq||!$('delete-dialog').open)return;state.preview=data;$('preview-status').textContent=data.files?'Đã kiểm tra. Bạn có thể xác nhận dọn.':data.journal?'Không có file thường đủ điều kiện. Journal sẽ được kiểm tra theo tuổi bản ghi.':'Không có file đủ điều kiện để dọn theo lựa chọn này.';$('journal-note').hidden=!data.journal;for(const [label,value] of [[data.journal?'File ước tính':'File sẽ xóa',data.files],['Dự kiến trên ổ',fmt(data.allocated)+(data.memory_allocated?' + '+fmt(data.memory_allocated)+' RAM':'')],['Giữ lại',data.skipped]]){const card=node('div');card.append(node('small',label),node('b',String(value)));$('preview-metrics').append(card);}$('confirm-delete').textContent='Xác nhận dọn';$('confirm-delete').disabled=data.journal?false:!data.files;if($('preview-expanded').open)await previewFiles();}catch(e){if(seq===state.previewSeq)$('preview-status').textContent=e.message;}}
  async function previewFiles(){if(!state.preview)return;const token=state.preview.token,skipped=state.showSkipped,page=state.previewPage;$('show-candidates').setAttribute('aria-pressed',String(!skipped));$('show-skipped').setAttribute('aria-pressed',String(skipped));try{const data=await api('preview-details',{token,page,skipped});if(state.preview?.token!==token||state.showSkipped!==skipped||state.previewPage!==page)return;state.previewPage=data.page;state.previewPages=data.pages;$('preview-files').replaceChildren(...data.files.map(f=>fileRow(f)));if(!data.files.length)$('preview-files').append(node('div',skipped?'Không có file bị bỏ qua.':'Không có file trong danh sách.','s-empty'));$('preview-page').textContent='Trang '+data.page+' / '+data.pages+' · '+data.total+' file';$('preview-prev').disabled=data.page<=1;$('preview-next').disabled=data.page>=data.pages;}catch(e){$('preview-status').textContent=e.message;$('confirm-delete').disabled=true;}}
  async function execute(){if(!state.preview||state.busy)return;state.busy=true;$('confirm-delete').disabled=true;$('preview-reload').disabled=true;$('days').disabled=true;const token=state.preview.token;state.previewSeq++;$('preview-status').textContent='Đang dọn dữ liệu; vui lòng chờ kết quả…';try{const result=await api('delete',{token,confirm:true});state.preview=null;state.busy=false;$('delete-dialog').close();$('detail-dialog').close();const box=$('result');box.hidden=false;box.replaceChildren(node('b','Đã hoàn tất lượt dọn dữ liệu.'));box.append(node('div','Đã xóa '+result.removed+' file ('+fmt(result.removed_bytes)+' nội dung) · Bỏ qua khi thực hiện '+result.skipped+' · Giữ lại từ xem trước '+result.kept+' · Lỗi '+result.error_count));for(const change of result.disk_changes)box.append(node('div','Ổ '+change.path+': dung lượng trống '+(change.delta>=0?'tăng ':'giảm ')+fmt(Math.abs(change.delta))+'.'));box.append(node('div','Chênh lệch dung lượng trống được đo lại và có thể chịu ảnh hưởng từ tiến trình khác.','s-note'));if(result.memory_removed)box.append(node('div','Đã dọn '+fmt(result.memory_removed)+' nội dung journal trong RAM.'));if(result.journal)box.append(node('div','Số file đã xóa được đo trước/sau khi journalctl chạy; có thể khác bản xem trước ước tính.','s-note'));if(result.errors.length){const list=node('ul');for(const error of result.errors)list.append(node('li',error));box.append(list);}await scan(true);box.scrollIntoView({behavior:'smooth'});}catch(e){$('preview-status').textContent=e.message+' · Bấm Xem trước lại để kiểm tra trạng thái hiện tại.';state.preview=null;}finally{state.busy=false;$('preview-reload').disabled=false;$('days').disabled=false;}}
  $('refresh').addEventListener('click',()=>scan(true));
  $('quick-clean').addEventListener('click',()=>openDelete());
  $('preview-expanded').addEventListener('toggle',()=>{if($('preview-expanded').open)previewFiles();});
  document.querySelectorAll('[data-s-group]').forEach(b=>b.addEventListener('click',()=>{
    state.group=b.dataset.sGroup;$('group').value=state.group;state.selected.clear();
    $('expanded').open=true;renderGroups();$('expanded').scrollIntoView({behavior:'smooth',block:'start'});
  }));
  for(const key of ['version','group'])$(key).addEventListener('change',()=>{state[key]=$(key).value;state.selected.clear();render();});
  $('search').addEventListener('input',()=>{state.selected.clear();renderGroups();});$('clear-selection').addEventListener('click',()=>{state.selected.clear();renderGroups();});$('bulk-delete').addEventListener('click',()=>openDelete([...state.selected]));
  $('delete-source').addEventListener('click',()=>openDelete([state.source.id]));$('delete-files').addEventListener('click',()=>openDelete([state.source.id],[...state.files]));$('select-page').addEventListener('change',()=>{for(const file of state.visibleFiles)$('select-page').checked?state.files.add(file.id):state.files.delete(file.id);loadFiles();});
  let searchTimer;$('file-search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.filePage=1;loadFiles();},250);});$('file-sort').addEventListener('change',()=>{state.filePage=1;loadFiles();});
  $('file-prev').addEventListener('click',()=>{if(state.filePage>1){state.filePage--;loadFiles();}});$('file-next').addEventListener('click',()=>{if(state.filePage<state.filePages){state.filePage++;loadFiles();}});
  $('days').addEventListener('change',preview);$('preview-reload').addEventListener('click',preview);$('confirm-delete').addEventListener('click',execute);
  $('show-candidates').addEventListener('click',()=>{state.showSkipped=false;state.previewPage=1;previewFiles();});$('show-skipped').addEventListener('click',()=>{state.showSkipped=true;state.previewPage=1;previewFiles();});
  $('preview-prev').addEventListener('click',()=>{if(state.previewPage>1){state.previewPage--;previewFiles();}});$('preview-next').addEventListener('click',()=>{if(state.previewPage<state.previewPages){state.previewPage++;previewFiles();}});
  scan();
})();
