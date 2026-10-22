/* Editable offline UX handoff. No production API calls; no secret storage. */
(() => {
  "use strict";
  const papers = [
    {id:11,title:"CaCl₂–vermiculite composite hydration kinetics",authors:"Demo Authors",year:2026,venue:"Applied Energy",status:"source ready (demo)",tags:["TCES","kinetics"],doi:"10.0000/example-11"},
    {id:12,title:"Packed-bed thermochemical heat delivery",authors:"Demo Authors",year:2025,venue:"Energy",status:"source ready (demo)",tags:["TCES","packed bed"],doi:"10.0000/example-12"},
    {id:13,title:"Sorption cycling of salt hydrates",authors:"Demo Authors",year:2024,venue:"Journal of Energy Storage",status:"metadata only (demo)",tags:["stability"],doi:"10.0000/example-13"}
  ];
  const resetState = () => ({view:"start",step:1,signedIn:false,keyStatus:"missing",relayOnline:false,browserReady:false,hostVerified:false,cloudCommitted:false,accessScopeId:"demo-device",probe:null,zotero:false,selected:[],query:"",tag:"",collection:"all",paperTags:papers.map(p=>[p.id,[...p.tags]])});
  let s=resetState();
  const $=id=>document.getElementById(id);
  const esc=v=>String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
  const tags=id=>s.paperTags.find(item=>item[0]===id)?.[1] || [];
  const b=(name,action,kind="")=>'<button type="button" class="'+(kind||"tool")+'" data-action="'+action+'">'+esc(name)+'</button>';
  const h=(title,desc)=>'<div class="eyebrow">YOUR RESEARCH, CONNECTED / DESIGN ONLY</div><h1>'+esc(title)+'</h1><p class="lead">'+esc(desc)+'</p>';
  const state=(label,good)=>'<div class="status '+(good?"ok":"")+'"><span class="dot"></span>'+esc(label)+'</div>';
  const ready=()=>MdteroDesignPolicy.readiness({signedIn:s.signedIn,keyStatus:s.keyStatus,relayOnline:s.relayOnline,browserReady:s.browserReady,hostVerified:s.hostVerified,cloudCommitted:s.cloudCommitted,accessScopeId:s.accessScopeId,probe:s.probe});
  function start(){
    const r=ready();
    const labels=["注册账户","配置文献访问","连接电脑与 AI"];
    const steps='<div class="steps">'+labels.map((v,i)=>'<button type="button" class="step '+(s.step===i+1?"active":"")+'" data-action="step-'+(i+1)+'"><span class="number">'+(r.steps[i]==="complete"?"✓":i+1)+'</span><span><b>'+v+'</b><small>'+({"complete":"已完成（模拟）","skipped":"已跳过","partial":"部分完成","pending":"待开始"}[r.steps[i]])+'</small></span></button>').join("")+'</div>';
    let content="";
    if(s.step===1)content='<article class="card"><h2>你的私人研究空间</h2><p>注册后先添加第一篇开放文献。5 GiB 是产品设计目标，不代表已自动开通云端额度。</p><label><input id="accept" type="checkbox"> 我已阅读模拟演示说明</label><div class="actions">'+b("模拟注册","register","primary")+'</div><div class="notice">无需真实账户。本页面不会上传数据或要求输入密钥。</div></article>';
    if(s.step===2)content='<article class="card"><h2>让你需要的来源能提供全文</h2><p>Elsevier 等出版社 API Key 属于文献访问凭据，不是模型 API Key。真实产品应该提供申请入口、遮挡输入和服务端校验。</p><div class="status"><span class="dot"></span>当前密钥：'+esc(s.keyStatus==="verified"?"模拟已验证":s.keyStatus==="skipped"?"已跳过":"未配置")+'</div><div class="actions">'+b("模拟密钥验证","verify-key","primary")+b("先用开放文献","skip-key")+b("下一步","step-3")+'</div><p class="hint">密钥有效不等于所有期刊有访问权；个人学校密码及 Cookie 不进入 Mdtero 云端。</p></article>';
    if(s.step===3)content='<div class="grid"><article class="card"><h2>Mdtero Connect</h2><p>本机后台负责授权的机构浏览器、Relay 以及 Zotero。真正安装状态应由设备回连确定。</p>'+state(s.relayOnline?"设备在线（模拟）":"设备离线",s.relayOnline)+b("模拟连接 Relay","relay-on","primary")+'</article><article class="card"><h2>连接你常用的 AI</h2><p>云端 MCP 与独立客户端共享文献和证据。OAuth/API Key 属于不同授权方式。</p>'+state(s.hostVerified?"AI 已连接（模拟）":"AI 未连接",s.hostVerified)+b("模拟授权","host-on","primary")+'</article></div><div class="actions">'+b("进入文献库","view-library","primary")+'</div>';
    return h("一处整理文献，随处继续研究。","注册、文献访问和设备连接分步骤完成。开放文献可以先用，额外能力按需要开启。")+steps+content;
  }
  function connections(){
    return h("连接状态，清楚可核验","设备在线、浏览器会话和具体论文授权必须分别验证。CARSI 学校密码及会话始终留在本机。")+
      '<div class="grid"><article class="card"><h2>校园与出版社</h2>'+
      state(s.relayOnline?"Relay 传输在线":"Relay 离线",s.relayOnline)+state(s.browserReady?"本机授权浏览器就绪":"本机浏览器未就绪",s.browserReady)+
      state(s.probe?"单篇全文已验证（模拟）":"尚无有效的文章全文证据",!!s.probe)+
      '<div class="actions">'+b("模拟机构登录","institution-login")+b("模拟单篇全文检查","article-probe")+b("模拟断开","relay-off")+'</div>'+
      '<p class="hint">校外 CARSI 登录不等于校园 IP；一篇论文的验证结果不能用于其他文章。</p></article>'+
      '<article class="card"><h2>Zotero 单向同步</h2><p>首版计划：从本机 Zotero 读取选定集合，预览 metadata 后由用户确认导入，不回写 Zotero，也不自动 OCR 附件。</p>'+
      state(s.zotero?"3 条书目已模拟同步":"尚未连接 Zotero",s.zotero)+
      b("模拟同步 3 条书目","zotero-sync","primary")+
      '<div class="notice">本页不访问 Zotero 本机端口；真正连接、同步检查点及去重仍待实现。</div></article></div>';
  }
  function library(){
    const match=p=>p.title.toLowerCase().includes(s.query.toLowerCase()) && (!s.tag||tags(p.id).includes(s.tag)) && (s.collection==="all" || (s.collection==="tces" && tags(p.id).includes("TCES")));
    const filtered=papers.filter(match);
    const selection=s.selected.filter(id=>papers.some(p=>p.id===id));
    const allTags=[...new Set(s.paperTags.flatMap(p=>p[1]))].sort();
    const list=filtered.map(p=>'<label class="listrow '+(selection.includes(p.id)?"selected":"")+'"><input type="checkbox" data-id="'+p.id+'" '+(selection.includes(p.id)?"checked":"")+'><span><b>'+esc(p.title)+'</b><small>'+esc(p.authors)+' · '+p.year+' · '+esc(p.venue)+'</small><small>'+esc(p.status)+' · '+tags(p.id).map(t=>'#'+esc(t)).join(" ")+'</small></span></label>').join("");
    return h("我的文献库","从这里筛选、标记和导出；选中论文后才进入可审计的 AI 证据流程。所有列出的论文均为演示样例。")+
      '<div class="split"><section class="pane"><header>收藏夹</header><div class="collection-list">'+
      b("全部文献","collection-all",s.collection==="all"?"active":"")+
      b("TCES Review","collection-tces",s.collection==="tces"?"active":"")+
      '<div class="label">标签筛选</div><div class="chipset"><button type="button" data-tag="">全部</button>'+allTags.map(t=>'<button type="button" data-tag="'+esc(t)+'" class="'+(s.tag===t?"active":"")+'">'+esc(t)+'</button>').join("")+'</div></div></section>'+
      '<section class="pane"><header>文献条目 · '+filtered.length+' 条（演示）</header><div style="padding:12px 16px"><input type="search" id="find-paper" placeholder="搜索文献标题" value="'+esc(s.query)+'" aria-label="搜索文献"></div>'+
      (list||'<p class="empty">没有匹配的演示文献</p>')+'</section>'+
      '<section class="pane"><header>条目与操作</header><div class="details"><p class="hint">已选 '+selection.length+' 篇 · 仅在本地模拟标签修改与 BibTeX 导出。</p><label class="label" for="new-tag">为选中条目添加标签</label><input id="new-tag" type="text" maxlength="40" placeholder="例如 Cycling stability"><div class="actions">'+b("添加标签","add-tag","primary")+b("移除当前筛选标签","remove-tag")+'</div>'+
      '<div class="label">批量导出</div><div class="actions">'+b("下载演示 BibTeX","export-bib")+b("下载演示 CSV","export-csv")+'</div>'+
      '<p class="hint">真实 BibTeX/CSL/MD/ZIP 下载已由后端 PR #43 提供接口；此 UI 尚未绑定生产 API，也没有图片包导出。</p></div></section></div>';
  }
  function storage(){
    return h("文献持久化，透明可控","5 GiB 为未来默认用户逻辑配额。原始 PDF 不默认长期存储；私人图片需要完成持久化和授权验证。")+
      '<article class="card"><h2>128 MiB / 5 GiB（全部为模拟）</h2><div class="meter"><span></span></div><p>Markdown 8 MiB · 图片 110 MiB · 历史版本与回收站 10 MiB</p><div class="notice">未实现用户全量迁移、原子空间预留、图片长期存储或 PostgreSQL 备份恢复。不可把本视图当作生产空间报告。</div></article>';
  }
  function settings(){
    return h("设置与扩展","轻量模式默认只包含本机采集、研究文献库与 MCP。研究模式的 agent、模型和工具权限可选开启。")+
      '<div class="grid"><section class="card"><h2>账号及文献来源</h2><p>当前仅模拟。</p>'+state(s.signedIn?"模拟登录":"未登录",s.signedIn)+state(s.keyStatus==="verified"?"出版社 Key 模拟已验证":"出版社 Key 未验证",s.keyStatus==="verified")+b("前往三步引导","view-start")+'</section>'+
      '<section class="card"><h2>研究模式 / Agent</h2><p>支持 API Key 或合规的 OAuth，工具调用须有读取/写入/付费任务分级授权。Pi/OpenCode 需先做隔离和权限验证。</p><div class="notice">未内置 Pi、OpenCode 或任何可调用模型的 Agent；此处只是设计入口。</div></section></div>';
  }
  function draw(){
    const nav=["start","library","connections","storage","settings"];
    document.querySelectorAll("[data-view]").forEach(el=>{const active=el.dataset.view===s.view;el.classList.toggle("active",active);el.setAttribute("aria-current",active?"page":"false");});
    $("current-account").textContent=s.signedIn?"demo@mdtero.example（模拟）":"未登录（演示）";
    $("screen").innerHTML=({start,library,connections,storage,settings}[s.view]||start)();
  }
  function download(name,mime,body){
    const url=URL.createObjectURL(new Blob([body],{type:mime}));const a=document.createElement("a");
    a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  document.addEventListener("click",ev=>{
    const el=ev.target.closest("button");if(!el||el.disabled)return;
    if(el.dataset.view){s.view=el.dataset.view;draw();return;}
    if(el.hasAttribute("data-tag")){s.tag=el.dataset.tag;draw();return;}
    const action=el.dataset.action;if(!action)return;
    if(action==="reset"){s=resetState();draw();return;}
    if(action.startsWith("view-")){s.view=action.slice(5);draw();return;}
    if(action.startsWith("step-")){s.step=Number(action.slice(5));s.view="start";draw();return;}
    if(action==="register"){if(!$("accept")?.checked){alert("请先确认模拟说明");return;}s.signedIn=true;s.cloudCommitted=true;s.step=2;}
    if(action==="verify-key"){s.keyStatus="verified";s.step=3;}
    if(action==="skip-key"){s.keyStatus="skipped";s.step=3;}
    if(action==="relay-on"){s.relayOnline=true;}
    if(action==="host-on"){s.hostVerified=true;}
    if(action==="relay-off"){s.relayOnline=false;s.browserReady=false;s.probe=null;}
    if(action==="institution-login"){s.relayOnline=true;s.browserReady=true;s.probe=null;}
    if(action==="article-probe"){if(!s.browserReady){alert("请先模拟机构登录");return;}s.probe={scopeId:s.accessScopeId,documentId:"example-paper",outcome:"full_text_ok",bodyVerified:true,ageSeconds:0};}
    if(action==="zotero-sync"){s.zotero=true;}
    if(action.startsWith("collection-")){s.collection=action.slice(11);}
    if(action==="add-tag"||action==="remove-tag"){
      const v=action==="remove-tag"?s.tag:$("new-tag")?.value.trim();
      if(!v||v.length>40||s.selected.length===0){alert("请选择论文和有效标签");return;}
      s.paperTags=s.paperTags.map(([id,old])=>!s.selected.includes(id)?[id,old]:[id,action==="add-tag"?[...new Set([...old,v])]:old.filter(t=>t!==v)]);
    }
    if(action==="export-bib"||action==="export-csv"){
      const selected=papers.filter(p=>s.selected.includes(p.id));
      if(!selected.length){alert("请先选择演示文献");return;}
      if(action==="export-csv"){download("mdtero-DEMO-references.csv","text/csv",["title,year,authors,doi",...selected.map(p=>[p.title,p.year,p.authors,p.doi].map(v=>'"'+String(v).replaceAll('"','""')+'"').join(","))].join("\n"));}
      else {download("mdtero-DEMO-references.bib","text/plain",selected.map(p=>"@article{mdteroDemo"+p.id+",\n  title = {{"+p.title+"}},\n  year = {"+p.year+"},\n  author = {"+p.authors+"},\n  doi = {"+p.doi+"}\n}").join("\n\n"));}
    }
    draw();
  });
  document.addEventListener("change",ev=>{const el=ev.target;if(!el.matches("[data-id]"))return;const id=Number(el.dataset.id);s.selected=el.checked?[...new Set([...s.selected,id])]:s.selected.filter(i=>i!==id);draw();});
  document.addEventListener("input",ev=>{if(ev.target.id!=="find-paper")return;const offset=ev.target.selectionStart;s.query=ev.target.value;draw();$("find-paper")?.focus();$("find-paper")?.setSelectionRange(offset,offset);});
  draw();
})();