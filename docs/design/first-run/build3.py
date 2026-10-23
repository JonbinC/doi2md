# mdtero 首次使用设计稿 v3：Zotero 式三栏骨架 + MCP UI 组件（砖红 tokens 换肤）+ 官网 logo。
# 数据来自 /workspace/ui-mock/graph-data.json；作者一律用「示例作者」占位，避免编造。
import json, html, pathlib, asyncio, base64
from playwright.async_api import async_playwright
OUT = pathlib.Path('/workspace/first-run'); H = OUT/'html3'; M = OUT/'mocks'
tokens = open('/workspace/mdtero-tokens.css').read()
comp = (OUT/'components.css').read_text()
KX = '/workspace/Nextmdtero/node_modules/.pnpm/katex@0.17.0/node_modules/katex/dist/'
LOGO = 'data:image/svg+xml;base64,' + base64.b64encode((OUT/'assets/brand-mark.svg').read_bytes()).decode()
D = json.load(open('/workspace/ui-mock/graph-data.json')); e = html.escape
VEN = {'rser':'Renewable and Sustainable Energy Reviews','solmat':'Solar Energy Materials and Solar Cells','egypro':'Energy Procedia','apenergy':'Applied Energy','renene':'Renewable Energy','enbuild':'Energy and Buildings','energy':'Energy','est':'Journal of Energy Storage','solener':'Solar Energy','matpr':'Materials Today: Proceedings','ces':'Chemical Engineering Science','cej':'Chemical Engineering Journal','applthermaleng':'Applied Thermal Engineering','ijheatmasstransfer':'Int. J. Heat Mass Transfer','enconman':'Energy Conversion and Management'}
def venue(doi):
    d = (doi or '').replace('https://doi.org/','')
    if d.startswith('10.3390/en'): return 'Energies'
    if d.startswith('10.3390/buildings'): return 'Buildings'
    if d.startswith('10.3390/app'): return 'Applied Sciences'
    if d.startswith('10.3390/ma'): return 'Materials'
    if d.startswith('10.1021/'): return 'ACS 期刊'
    if d.startswith('10.1039/'): return 'RSC 期刊'
    if d.startswith('10.1016/j.'): return VEN.get(d.split('j.')[1].split('.')[0], 'Elsevier 期刊')
    return None
P = []
for n in D['nodes']:
    v = venue(n.get('doi'))
    if v and n.get('y'): P.append({**n, 'v': v, 'd': n['doi'].replace('https://doi.org/','')})
AU = ['示例作者 A 等','示例作者 B 等','示例作者 C','示例作者 D 等','示例作者 E 等','示例作者 F','示例作者 G 等','示例作者 H 等']
DATES = ['2026/10/22','2026/10/21','2026/10/21','2026/10/20','2026/10/18','2026/10/15','2026/10/12','2026/10/09','2026/10/02','2026/09/28','2026/09/26','2026/09/20','2026/09/14','2026/09/10','2026/09/03','2026/08/30','2026/08/22','2026/08/15','2026/08/09','2026/08/01','2026/07/26']
I = {k: f'<svg class="i" viewBox="0 0 24 24">{v}</svg>' for k, v in {
 'search':'<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
 'lib':'<path d="M4 19V5a1 1 0 0 1 1-1h3v15H5a1 1 0 0 1-1-1Z"/><path d="M8 4h4v15H8"/><path d="m13 5 4-1 3 14-4 1Z"/>',
 'import':'<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
 'plus':'<path d="M12 5v14M5 12h14"/>','clock':'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
 'folder':'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
 'doc':'<path d="M7 3h7l5 5v13H7Z"/><path d="M14 3v5h5"/>','trash':'<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14"/>',
 'spark':'<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
 'chev':'<path d="m9 6 6 6-6 6"/>','down':'<path d="m6 9 6 6 6-6"/>','check':'<path d="m5 12 5 5 9-10"/>',
 'pause':'<path d="M9 5v14M15 5v14"/>','x':'<path d="M6 6l12 12M18 6 6 18"/>','alert':'<path d="M12 3 2 20h20Z"/><path d="M12 10v4M12 17v.5"/>',
 'chrome':'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/><path d="M12 8.5h8M8.9 13.8 5 7M15.1 13.8 11 21"/>',
 'route':'<circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="6" r="2.5"/><path d="M8.5 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.5"/>',
 'monitor':'<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
 'edit':'<path d="M4 20h4L19 9l-4-4L4 16Z"/>','export':'<path d="M12 15V3M7 8l5-5 5 5"/><path d="M5 14v6h14v-6"/>',
 'tag':'<path d="M3 12V4h8l10 10-8 8Z"/><circle cx="7.5" cy="8.5" r="1.3"/>','open':'<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v6H4V6h6"/>',
 'info':'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>','abs':'<path d="M5 5h14M5 10h14M5 15h9M5 20h6"/>',
 'note':'<path d="M5 4h14v11l-5 5H5Z"/><path d="M14 20v-5h5"/>','link':'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
 'send':'<path d="M4 12 20 4l-6 16-3-7Z"/>','table':'<rect x="3" y="5" width="18" height="14" rx="1.5"/><path d="M3 10h18M9 5v14"/>',
 'compare':'<path d="M8 4v16M16 4v16M4 8h4M16 16h4"/>','dots':'<circle cx="6" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="18" cy="12" r="1"/>',
 'user':'<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4.5-6 8-6s7 2 8 6"/>','gear':'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>',
 'shield':'<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6Z"/>','bolt':'<path d="M13 3 5 14h6l-1 7 8-11h-6Z"/>',
 'filter':'<path d="M3 5h18l-7 8v6l-4 2v-8Z"/>','up':'<path d="m6 15 6-6 6 6"/>','book':'<path d="M4 5a2 2 0 0 1 2-2h14v16H6a2 2 0 0 0-2 2Z"/><path d="M4 21V5"/>',
}.items()}
STATE_ICON = {
 'ready': ('ok', '<circle cx="12" cy="12" r="8"/><path d="m8.5 12 2.5 2.5 4.5-5"/>', '全文已就绪'),
 'meta': ('quiet', '<path d="M7 3h7l5 5v13H7Z" stroke-dasharray="3 2"/>', '仅元数据'),
 'queued': ('quiet', '<circle cx="12" cy="12" r="8" stroke-dasharray="3 3"/>', '排队中'),
 'busy': ('accent', '<path d="M12 4a8 8 0 1 1-8 8"/>', '获取中'),
 'fail': ('error', '<circle cx="12" cy="12" r="8"/><path d="M12 8v5M12 16v.5"/>', '获取失败'),
 'warn': ('warn', '<path d="M12 3 2 20h20Z"/><path d="M12 10v4M12 17v.5"/>', '等待验证 · 需要在 Chrome 里完成验证'),
 'metafail': ('quiet', '<path d="M7 3h7l5 5v13H7Z" stroke-dasharray="3 2"/><circle cx="18" cy="18" r="3.2" fill="var(--error)" stroke="none"/>', '仅元数据 · 出版社未开放全文'),
}
def sicon(k):
    c, p, t = STATE_ICON[k]
    return f'<span class="si {c}" title="{t}"><svg viewBox="0 0 24 24">{p}</svg></span>'
PILL = {'ready':'全文已就绪','meta':'仅元数据','queued':'排队中','busy':'获取中','fail':'获取失败','warn':'等待验证','metafail':'仅元数据'}
def pill(k): return f'<span class="pill {k}">{"<span class=spin></span>" if k=="busy" else ""}{PILL[k]}</span>'
CSS = '''
.win{width:1280px;height:800px;display:flex;flex-direction:column;background:var(--bg);position:relative;overflow:hidden}
.tabs{height:40px;flex:none;display:flex;align-items:flex-end;gap:2px;padding:0 12px 0 84px;background:var(--bg);border-bottom:1px solid var(--line);position:relative}
.lights{position:absolute;left:14px;top:14px;display:flex;gap:8px}.lights i{width:12px;height:12px;border-radius:50%;background:var(--line);border:1px solid var(--line)}
.tab{height:31px;display:flex;align-items:center;gap:7px;padding:0 12px;max-width:230px;border:1px solid transparent;border-bottom:0;border-radius:8px 8px 0 0;font-size:12px;color:var(--quiet);white-space:nowrap}
.tab span.t{overflow:hidden;text-overflow:ellipsis}
.tab.on{background:var(--surface);color:var(--ink);border-color:var(--line);font-weight:600;margin-bottom:-1px;height:32px}
.tab .x{opacity:.6;display:flex}.tab .x svg{width:12px;height:12px}
.tab img{width:16px;height:16px}
.panes{flex:1;min-height:0;display:grid;grid-template-columns:230px minmax(0,1fr) 352px}
.lp{background:var(--muted);border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0}
.tree{flex:1;overflow:hidden;padding:8px 6px}
.ti{display:flex;align-items:center;gap:7px;height:26px;padding:0 8px;border-radius:6px;font-size:13px;color:var(--ink);white-space:nowrap}
.ti .n{margin-left:auto;font-size:11px;color:var(--quiet)}
.ti svg.i{width:15px;height:15px;color:var(--quiet)}
.ti.on{background:var(--accent-soft);color:var(--accent-ink);font-weight:600}.ti.on svg.i{color:var(--accent)}
.ti .tw{width:12px;display:flex;color:var(--quiet)}.ti .tw svg{width:11px;height:11px}
.tagbox{border-top:1px solid var(--line);padding:8px 10px 8px;font-size:12px}
.ctags{display:flex;flex-wrap:wrap;gap:4px 10px;margin-bottom:6px}.ctags span{display:flex;align-items:center;gap:5px}.ctags i{width:9px;height:9px;border-radius:50%}
.ptags{color:var(--quiet);line-height:19px;height:38px;overflow:hidden}
.tagf{margin-top:6px;height:26px;border:1px solid var(--line);border-radius:6px;background:var(--surface);display:flex;align-items:center;gap:6px;padding:0 8px;color:var(--quiet);font-size:12px}
.acct{border-top:1px solid var(--line);height:48px;flex:none;display:flex;align-items:center;gap:9px;padding:0 12px}
.acct .av{width:28px;height:28px;border-radius:50%;background:var(--accent-soft);color:var(--accent-ink);display:grid;place-items:center;font-weight:650;font-size:13px}
.acct .nm{display:grid;line-height:16px;font-size:13px}.acct .nm small{font-size:11px;color:var(--quiet)}
.acct svg.i{margin-left:auto;color:var(--quiet)}
.mp{display:flex;flex-direction:column;min-width:0;min-height:0;background:var(--surface);position:relative}
.tb{height:46px;flex:none;display:flex;align-items:center;gap:6px;padding:0 10px;border-bottom:1px solid var(--line)}
.tb .srch{margin-left:auto;width:214px;height:28px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--muted);display:flex;align-items:center;gap:6px;padding:0 8px;font-size:12px;color:var(--quiet);white-space:nowrap;overflow:hidden}
.tb .srch b{font-weight:500;color:var(--ink)}
.tb .vr{width:1px;height:20px;background:var(--line);margin:0 2px}
table.zt{width:100%;border-collapse:collapse;table-layout:fixed;font-size:12.5px}
table.zt th{height:28px;font-size:11.5px;font-weight:600;color:var(--quiet);text-align:left;padding:0 8px;border-bottom:1px solid var(--line);border-right:1px solid var(--line);background:var(--surface);white-space:nowrap;overflow:hidden}
table.zt th:last-child{border-right:0}
table.zt th .ar{float:right;display:flex;margin-top:6px}table.zt th .ar svg{width:12px;height:12px}
table.zt td{height:28px;padding:0 7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--ink)}
table.zt tr:nth-child(even) td{background:color-mix(in srgb,var(--muted) 55%,transparent)}
table.zt tr.sel td{background:var(--accent-soft);color:var(--accent-ink)}
table.zt tr.focus td{background:var(--accent);color:var(--on-accent)}
table.zt tr.focus .si{color:var(--on-accent)!important}
table.zt td.c0{padding:0 0 0 9px}
.si{display:inline-flex;vertical-align:middle}.si svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
.si.ok{color:var(--ok)}.si.quiet{color:var(--quiet)}.si.accent{color:var(--accent)}.si.error{color:var(--error)}.si.warn{color:var(--warn)}
.rp{border-left:1px solid var(--line);background:var(--surface);display:flex;flex-direction:column;min-height:0;position:relative}
.rtabs{height:46px;flex:none;display:flex;align-items:center;padding:0 12px;border-bottom:1px solid var(--line);gap:8px}
.seg{display:flex;flex:1;background:var(--muted);border:1px solid var(--line);border-radius:var(--r-sm);padding:2px;height:32px}
.seg span{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;border-radius:6px;font-size:12.5px;color:var(--quiet);font-weight:550}
.seg span.on{background:var(--surface);color:var(--ink);box-shadow:var(--shadow-card);border:1px solid var(--line)}
.seg span.on.ai{color:var(--accent-ink)}.seg svg.i{width:14px;height:14px}
.rbody{flex:1;min-height:0;display:flex}
.rcont{flex:1;min-width:0;overflow:hidden;padding:14px 14px 14px 16px}
.vnav{width:38px;flex:none;border-left:1px solid var(--line);display:flex;flex-direction:column;align-items:center;gap:6px;padding-top:10px}
.vnav span{width:28px;height:28px;border-radius:7px;display:grid;place-items:center;color:var(--quiet)}.vnav span.on{background:var(--accent-soft);color:var(--accent)}
.vnav svg.i{width:16px;height:16px}
.ititle{font-size:15px;line-height:21px;font-weight:650;margin:0 0 10px}
.sech{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:650;color:var(--ink);margin:12px 0 8px}.sech svg.i{width:13px;height:13px;color:var(--quiet)}
.kv{display:grid;grid-template-columns:66px 1fr;gap:5px 10px;font-size:12.5px;line-height:18px}.kv dt{color:var(--quiet);text-align:right}.kv dd{margin:0;min-width:0;overflow-wrap:anywhere}
.ftbox{border:1px solid var(--line);border-radius:var(--r-md);padding:10px 12px;background:var(--muted);font-size:12px}
.sbar{height:30px;flex:none;display:flex;align-items:center;gap:10px;padding:0 12px;border-top:1px solid var(--line);background:var(--surface);font-size:12px;color:var(--quiet);white-space:nowrap}
.sbar .prog{width:120px;height:5px}
.sbar b{color:var(--ink);font-weight:600}
.sbar .r{margin-left:auto;display:flex;align-items:center;gap:8px}
.sbtn{display:inline-flex;align-items:center;gap:4px;color:var(--ink);padding:2px 6px;border-radius:5px;border:1px solid var(--line);background:var(--surface);font-size:11.5px}.sbtn svg.i{width:12px;height:12px}
.chip{display:inline-flex;align-items:center;gap:5px;height:24px;padding:0 8px;border-radius:999px;background:var(--accent-soft);color:var(--accent-ink);font-size:11.5px;white-space:nowrap;max-width:132px}
.chip span{overflow:hidden;text-overflow:ellipsis}.chip svg.i{width:11px;height:11px;flex:none}
.pcard{border:1px solid var(--line);border-radius:var(--r-md);padding:10px 11px;background:var(--surface);display:grid;gap:2px;font-size:12px}
.pcard b{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--ink)}.pcard b svg.i{color:var(--accent);width:15px;height:15px}
.pcard span{color:var(--quiet);font-size:11.5px;line-height:16px}
.msg-u{align-self:flex-end;background:var(--accent-soft);color:var(--accent-ink);border-radius:12px 12px 4px 12px;padding:8px 11px;font-size:12.5px;line-height:19px;max-width:86%}
.step{border:1px solid var(--line);border-radius:var(--r-sm);background:var(--muted);font-size:12px}
.step .h{display:flex;align-items:center;gap:7px;height:30px;padding:0 10px;color:var(--ink)}
.step .h .t{margin-left:auto;color:var(--quiet);font-size:11px}
.step .b{border-top:1px solid var(--line);padding:6px 10px 8px 30px;color:var(--quiet);font-size:11.5px;line-height:18px}
.ok-c{color:var(--ok)}.acc-c{color:var(--accent)}
.inbox{border:1px solid var(--line);border-radius:var(--r-md);background:var(--surface);box-shadow:var(--shadow-pop);padding:9px 10px;display:grid;gap:8px}
.inbox .ph{font-size:12.5px;color:var(--quiet);min-height:36px;line-height:18px}
.inbox .f{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--quiet)}
.inbox .send{margin-left:auto;width:30px;height:30px;border-radius:var(--r-sm);background:var(--accent);color:var(--on-accent);display:grid;place-items:center}
.md h3{font-size:14px;margin:12px 0 6px}.md p,.md li{font-size:13px;line-height:21px}.md ul{padding-left:18px;margin:4px 0}
.md table{border-collapse:collapse;width:100%;font-size:12px;margin:6px 0}.md th,.md td{border:1px solid var(--line);padding:4px 6px;text-align:left}.md th{background:var(--muted)}
.md sup{color:var(--accent);font-size:10px}
.gate{position:absolute;inset:40px 0 0 0;display:grid;place-items:center;background:var(--bg)}
.authcard{width:420px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--shadow-pop);padding:28px 28px 22px}
.brandrow{display:flex;align-items:center;gap:10px;margin-bottom:18px}.brandrow img{width:36px;height:36px}.brandrow b{font-size:18px;letter-spacing:-.3px;display:block;line-height:20px}.brandrow small{font-size:11px;color:var(--quiet)}
.sheetwrap{position:absolute;inset:0;background:rgba(28,22,18,.34);display:grid;place-items:center;z-index:20}
.sheet{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--shadow-pop);padding:22px 24px}
.sheet header{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.sheet h2{margin:0}
.steps3{display:grid;gap:10px}.steps3 div{display:flex;gap:10px;align-items:flex-start;font-size:12.5px;line-height:18px}.steps3 em{font-style:normal;width:20px;height:20px;border-radius:50%;background:var(--accent-soft);color:var(--accent-ink);display:grid;place-items:center;font-size:11px;font-weight:700;flex:none}
.cnt{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 10px}
.prow2{display:flex;align-items:center;gap:10px;height:30px;border-bottom:1px solid var(--line);font-size:12.5px}.prow2 .t{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.swin{position:absolute;inset:0;display:grid;grid-template-columns:200px 1fr;background:var(--surface)}
.snav{background:var(--muted);border-right:1px solid var(--line);padding:52px 10px 10px}
.snav .ti{height:32px;font-size:13px}
.sbody{padding:52px 40px 30px;overflow:hidden}
.sbody h1{font-size:22px;line-height:30px;margin:0 0 4px}
.sec{max-width:720px;border:1px solid var(--line);border-radius:var(--r-md);background:var(--surface);padding:0 18px;margin-bottom:18px}
.srow{display:flex;align-items:center;gap:12px;padding:13px 0;border-bottom:1px solid var(--line);font-size:13px}.srow:last-child{border-bottom:0}
.srow .lbl{display:grid;line-height:19px;min-width:0}.srow .lbl small{font-size:12px;color:var(--quiet)}
.srow .rt{margin-left:auto;display:flex;align-items:center;gap:8px;flex:none}
.pic{width:32px;height:32px;border-radius:var(--r-sm);background:var(--muted);border:1px solid var(--line);display:grid;place-items:center;font-size:11px;font-weight:700;color:var(--quiet);flex:none}.pic.acc{background:var(--accent-soft);color:var(--accent);border-color:transparent}
.stitle{font-size:14px;font-weight:650;margin:0 0 4px}.sdesc{font-size:12px;color:var(--quiet);margin:0 0 10px}
.badge{display:inline-flex;align-items:center;height:18px;padding:0 6px;border-radius:999px;font-size:10.5px;font-weight:600;margin-left:6px;vertical-align:1px}
.badge.exp{background:var(--warn-soft);color:var(--warn)}.badge.ok{background:var(--ok-soft);color:var(--ok)}.badge.acc{background:var(--accent-soft);color:var(--accent-ink)}
.radio{width:16px;height:16px;border-radius:50%;border:1.5px solid var(--line);flex:none;display:grid;place-items:center}.radio.on{border-color:var(--accent)}.radio.on:after{content:"";width:8px;height:8px;border-radius:50%;background:var(--accent)}
.toast{position:absolute;z-index:30}
'''
def page(name, theme, body, head='', script=''):
    doc = f'<!doctype html><html lang="zh-CN" data-theme="{theme}"><head><meta charset="utf-8">{head}<style>{tokens}{comp}{CSS}</style></head><body><div class="win">{body}</div><span class="example" style="left:auto;right:14px;top:14px;bottom:auto">示例数据 · 设计稿</span>{script}</body></html>'
    (H/f'{name}-{theme}.html').write_text(doc)
def tabs(extra=(), on=0):
    t = [('lib', '文献库')] + list(extra)
    out = '<div class="lights"><i></i><i></i><i></i></div>'
    for i, (k, label) in enumerate(t):
        ic = f'<img src="{LOGO}" alt="">' if k == 'lib' else (I['spark'] if k == 'ai' else I['doc'])
        x = '' if k == 'lib' else f'<span class="x">{I["x"]}</span>'
        out += f'<div class="tab{" on" if i == on else ""}">{ic}<span class="t">{e(label)}</span>{x}</div>'
    return f'<div class="tabs">{out}</div>'
def tree(active='all', counts=(128, 6), empty=False):
    def ti(k, ic, label, n='', lvl=0, tw=''):
        tws = f'<span class="tw">{I[tw]}</span>' if tw else '<span class="tw"></span>'
        return f'<div class="ti{" on" if k == active else ""}" style="padding-left:{8 + lvl * 14}px">{tws}{I[ic]}<span>{label}</span><span class="n">{n}</span></div>'
    if empty:
        t = ti('all', 'lib', '我的文献库', '0', tw='down') + ti('recent', 'clock', '最近阅读', '', 1) + ti('trash', 'trash', '回收站', '', 1)
    else:
        t = (ti('all', 'lib', '我的文献库', counts[0], tw='down') + ti('recent', 'clock', '最近阅读', counts[1], 1) +
             ti('c1', 'folder', '盐水合物储热', 23, 1, 'down') + ti('c11', 'folder', 'CaCl2 复合材料', 9, 2) + ti('c12', 'folder', '蛭石载体', 6, 2) +
             ti('c2', 'folder', '吸附热力学', 14, 1, 'chev') + ti('c3', 'folder', '反应器与系统', 18, 1, 'chev') + ti('c4', 'folder', '综述待读', 9, 1) +
             ti('c5', 'folder', '组会 2026 秋', 7, 1) + ti('unf', 'doc', '未分类', 12, 1) + ti('trash', 'trash', '回收站', '', 1))
    tags = '' if empty else '''<div class="tagbox"><div class="ctags"><span><i style="background:var(--error)"></i>精读</span><span><i style="background:var(--ok)"></i>已读</span><span><i style="background:var(--warn)"></i>待读</span><span><i style="background:var(--accent)"></i>组会</span></div>
<div class="ptags">CaCl2 · 蛭石 · 水合反应 · 吸附等温线 · 动力学 · 循环稳定性 · 填充床 · 季节储热 · 湿度</div><div class="tagf">''' + I['search'] + '筛选标签</div></div>'
    acct = f'<div class="acct"><span class="av">J</span><span class="nm">Jianbin<small>已登录 · 账号与设置</small></span>{I["gear"]}</div>'
    return f'<aside class="lp"><div class="tree">{t}</div>{tags}{acct}</aside>'
def toolbar(status_label='全部', q='', scope='文献库'):
    s = f'{I["search"]}<span>{scope} ▾</span><span style="color:var(--line)">|</span>' + (f'<b>{e(q)}</b>' if q else '<span>标题、作者、DOI…</span>')
    return (f'<div class="tb"><a class="btn sm" title="从 Zotero 导入">{I["import"]}导入</a><a class="btn sm">{I["import"]}获取全文</a>'
            f'<a class="btn sm primary">{I["spark"]}用 AI 研究</a><span class="vr"></span><a class="btn sm quiet">{I["filter"]}全文状态：{status_label}</a><div class="srch">{s}</div></div>')
ROWSTAT = ['ready','busy','queued','queued','ready','metafail','meta','queued','ready','meta','ready','queued','meta','ready','queued','ready','ready','meta','ready','meta','ready','ready','meta']
TYPES = ['期刊文章'] * 6 + ['综述'] + ['期刊文章'] * 5 + ['会议论文'] + ['期刊文章'] * 10
def table(rows=None, sel=(), focus=None, stat=None, n=22):
    stat = stat or ROWSTAT; rows = rows or P[:n]
    h = (f'<tr><th style="width:30px" title="全文状态">{sicon("ready").replace("si ok","si quiet")}</th><th>标题</th><th style="width:52px">年</th><th style="width:96px">作者</th><th style="width:70px">类型</th><th style="width:124px">出版物</th>'
         f'<th style="width:90px">添加日期<span class="ar">{I["down"]}</span></th></tr>')
    b = ''
    for i, p in enumerate(rows):
        cls = 'focus' if i == focus else ('sel' if i in sel else '')
        b += f'<tr class="{cls}"><td class="c0">{sicon(stat[i % len(stat)])}</td><td title="{e(p["t"])}">{e(p["t"])}</td><td>{p["y"]}</td><td>{AU[i % len(AU)]}</td><td>{TYPES[i % len(TYPES)]}</td><td>{e(p["v"])}</td><td>{DATES[i % len(DATES)]}</td></tr>'
    return f'<div style="flex:1;min-height:0;overflow:hidden"><table class="zt">{h}{b}</table></div>'
def rtabs(ai=False, n=None):
    lab = f'mdtero AI{" · " + str(n) + " 篇" if n else ""}'
    return f'<div class="rtabs"><div class="seg"><span class="{"" if ai else "on"}">{I["info"]}信息</span><span class="ai {"on" if ai else ""}">{I["spark"]}{lab}</span></div></div>'
def vnav(on='info'):
    return '<div class="vnav">' + ''.join(f'<span class="{"on" if k == on else ""}" title="{t}">{I[k]}</span>' for k, t in [('info','信息'),('abs','摘要'),('note','笔记'),('tag','标签'),('link','相关')]) + '</div>'
def info_pane(p, st='ready', route='本机直连'):
    ft = {'ready': f'{pill("ready")}<div class="micro quiet" style="margin-top:6px">来源：出版社 XML · 经由：{route}</div><div style="display:flex;gap:6px;margin-top:8px"><a class="btn sm primary">{I["book"]}打开阅读</a><a class="btn sm">{I["spark"]}用 mdtero AI 总结</a></div>',
          'meta': f'{pill("meta")}<div class="micro quiet" style="margin-top:6px">还没有全文。获取时会按顺序排队，不占你的操作。</div><div style="display:flex;gap:6px;margin-top:8px"><a class="btn sm primary">{I["import"]}获取全文</a></div>',
          'metafail': f'{pill("meta")} <span class="small" style="color:var(--error)">· 出版社未开放全文</span><div class="micro quiet" style="margin-top:6px">上次获取没成功（10/23 17:42）。登录学校账号或换个全文出口后可以再试。</div><div style="display:flex;gap:6px;margin-top:8px"><a class="btn sm primary">{I["import"]}重试</a><a class="btn sm">{I["route"]}换全文出口</a></div>'}[st]
    return f'''<div class="rcont"><div class="ititle">{e(p["t"])}</div>
<div class="sech">{I["down"]}全文</div><div class="ftbox">{ft}</div>
<div class="sech">{I["down"]}信息</div><dl class="kv" style="margin:0"><dt>条目类型</dt><dd>期刊文章</dd><dt>作者</dt><dd>示例作者 A</dd><dt></dt><dd>示例作者 B</dd><dt>出版物</dt><dd>{e(p["v"])}</dd><dt>日期</dt><dd>{p["y"]}</dd><dt>DOI</dt><dd style="color:var(--accent)">{e(p["d"])}</dd><dt>被引</dt><dd>{p["c"]}</dd><dt>添加日期</dt><dd>2026/10/21 14:02</dd><dt>标签</dt><dd><span class="chip" style="height:20px">CaCl2</span> <span class="chip" style="height:20px">蛭石</span></dd></dl>
<div class="sech">{I["chev"]}摘要</div><div class="sech">{I["chev"]}笔记 <span class="quiet" style="font-weight:400">1</span></div></div>'''
def statusbar(left='', right=''):
    return f'<div class="sbar">{left}<span class="r">{right}</span></div>'
QUEUE = (f'<span class="spin" style="color:var(--accent)"></span><b>正在获取全文 5/12</b><span>· 经由 实验室台式机</span><span class="prog"><i style="width:42%"></i></span>'
         f'<span class="small quiet">已完成 4 · <span style="color:var(--error)">获取失败 1</span></span><span class="sbtn">{I["pause"]}暂停</span><span class="sbtn">取消</span><a style="color:var(--accent)">只看这批</a>')
def win3(tabsh, left, mid, right, sbar=''):
    return f'{tabsh}<div class="panes">{left}<main class="mp">{mid}</main><aside class="rp">{right}</aside></div>{sbar}'
# ---------------- screens ----------------
def s_login(th):
    body = f'''<div class="tabs" style="border-bottom:0"><div class="lights"><i></i><i></i><i></i></div></div>
<div class="gate"><div class="authcard"><div class="brandrow"><img src="{LOGO}" alt="mdtero"><div><b>mdtero</b><small>文献库 · 全文 · mdtero AI</small></div></div>
<h1 style="font-size:22px;line-height:30px;margin:0 0 6px">登录 mdtero</h1><p class="small quiet" style="margin:0 0 18px">登录后同步你的文献库，就能导入文献、获取全文，并用 mdtero AI 读论文。</p>
<a class="btn primary lg block">{I["open"]}在浏览器中登录</a>
<p class="micro quiet" style="margin:10px 0 0;text-align:center">会打开系统浏览器，登录完成后自动回到这里。</p>
<div style="height:1px;background:var(--line);margin:18px 0 12px"></div>
<div style="display:flex;justify-content:space-between;align-items:center" class="small"><a style="color:var(--accent)">还没有账号？注册</a><span class="quiet">中文 / EN</span></div></div>
<div style="position:absolute;bottom:18px;left:0;right:0;text-align:center" class="micro quiet">mdtero 0.1.0 内测版 · 帮助 · 隐私</div></div>'''
    page('01-login', th, body)
def empty_info():
    return f'<div class="rcont" style="display:grid;place-items:center;text-align:center"><div><div class="pic" style="width:48px;height:48px;margin:0 auto 10px">{I["doc"]}</div><b style="font-size:14px">选择一篇文献</b><p class="small quiet" style="margin:4px 0 0">右侧显示信息；选中多篇时<br>可以直接交给 mdtero AI。</p></div></div>'
def s_welcome(th):
    mid = f'''{toolbar()}<div style="flex:1;display:grid;place-items:center"><div style="text-align:center"><h1 style="font-size:22px;line-height:30px;margin:0 0 6px">欢迎，Jianbin。从哪里开始？</h1><p class="small quiet" style="margin:0 0 22px">只在第一次出现。之后随时可以点工具栏的「导入」。</p>
<div style="display:flex;gap:16px;justify-content:center;text-align:left">
<div class="choice hover" style="width:290px"><span class="ic">{I["import"]}</span><h2>从 Zotero 导入</h2><p>拖入 Zotero 导出的文件，先预览、确认后才导入。只导入题录信息，全文之后按需获取。</p><span class="go">选择导出文件 {I["chev"]}</span></div>
<div class="choice" style="width:290px"><span class="ic">{I["plus"]}</span><h2>新建空文献库</h2><p>起个名字就能开始，接着带你检索并加入第一篇论文。</p><span class="go">新建 {I["chev"]}</span></div></div>
<p class="micro quiet" style="margin:22px 0 0;visibility:hidden">检测到本机 Zotero（预留位）</p></div></div>'''
    sb = statusbar('<span class="spin" style="color:var(--accent)"></span><span>正在连接你的 Chrome…</span>')
    page('02-welcome', th, win3(tabs(), tree(empty=True), mid, rtabs() + f'<div class="rbody">{empty_info()}</div>', sb))
def s_import(th):
    rows = ''.join(f'<div class="prow2"><span class="micro quiet" style="width:18px">{i+1}</span><span class="t">{e(p["t"])}</span><span class="micro quiet" style="width:150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{e(p["v"])} · {p["y"]}</span>{"<span class=\"pill warn\">重复</span>" if i == 3 else "<span class=\"pill ready\">可导入</span>"}</div>' for i, p in enumerate(P[:9]))
    sheet = f'''<div class="sheetwrap"><div class="sheet" style="width:900px"><header><h2>从 Zotero 导入</h2><span class="quiet">{I["x"]}</span></header>
<div style="display:grid;grid-template-columns:270px minmax(0,1fr);gap:20px">
<div><div class="drop filled" style="padding:12px 14px;gap:12px"><span class="pic acc">{I["doc"]}</span><div style="display:grid;line-height:18px;min-width:0"><b style="font-size:13px">我的文库.bib</b><span class="micro quiet">1.8 MB · 612 篇 · 分 2 批</span></div><a class="btn text sm" style="margin-left:auto">换一个</a></div>
<p class="micro quiet" style="margin:8px 0 14px">支持 BibTeX、RIS、Zotero JSON、CSL JSON。Zotero RDF 暂不支持，请改导出 BibTeX。</p>
<div class="stitle" style="font-size:13px">怎么从 Zotero 导出</div><div class="steps3" style="margin-top:8px"><div><em>1</em><span>在 Zotero 里右键「我的文库」或某个分类</span></div><div><em>2</em><span>选「导出文库…」</span></div><div><em>3</em><span>格式选 BibTeX，点确定</span></div></div>
<div class="field" style="margin-top:16px"><label class="small" style="font-weight:600">导入到</label><div class="input" style="height:32px;font-size:13px">我的文献库 / 新分类「我的文库」<span style="margin-left:auto" class="quiet">{I["down"]}</span></div></div></div>
<div><div style="display:flex;align-items:baseline;gap:8px"><b style="font-size:15px">共 612 篇</b><span class="small quiet">预览前 30 篇</span></div>
<div class="cnt"><span class="pill busy">可导入 587</span><span class="pill meta">已存在 0</span><span class="pill warn">重复 14</span><span class="pill meta">跳过 11</span><span class="micro quiet" style="align-self:center">跳过：没有标题或 DOI 的条目</span></div>
<div style="border-top:1px solid var(--line)">{rows}</div>
<div style="display:flex;align-items:center;gap:10px;margin-top:10px"><span class="prog" style="width:160px"><i style="width:100%"></i></span><span class="micro quiet">已读取 2/2 批</span></div></div></div>
<div style="display:flex;align-items:center;gap:8px;margin-top:16px;padding-top:14px;border-top:1px solid var(--line)"><span class="micro quiet">只导入题录信息，不会自动获取全文。</span><a class="btn" style="margin-left:auto">取消</a><a class="btn primary">导入到文献库（587 篇）</a></div></div></div>'''
    page('03-import-preview', th, win3(tabs(), tree(empty=True), toolbar(), rtabs() + f'<div class="rbody">{empty_info()}</div>') + sheet)
def ctxmenu(x, y, n=1):
    it = lambda ic, t, k='', cls='': f'<div class="it {cls}">{I[ic]}<span>{t}</span><span class="k">{k}</span></div>'
    return (f'<div class="menu" style="left:{x}px;top:{y}px">' + it('book', '打开阅读', '↵') + it('spark', '用 mdtero AI 研究', '最多 10 篇') +
            '<div class="sep"></div>' + it('import', f'获取全文{"（" + str(n) + " 篇）" if n > 1 else ""}', '⌘⇧F', 'on') + '<div class="sep"></div>' +
            it('folder', '加入分类', '▸') + it('tag', '添加标签…') + it('trash', '移到回收站…', '⌫') + '<div class="sep"></div>' +
            it('export', '导出 Markdown…') + it('export', '导出 BibTeX…') + it('open', '在出版社页面打开', '', 'dis') + '</div>')
def s_library(th):
    mid = toolbar() + table(focus=5)
    right = rtabs() + f'<div class="rbody">{info_pane(P[5], "metafail")}{vnav()}</div>'
    page('04-library', th, win3(tabs(), tree(), mid, right, statusbar(QUEUE)) + ctxmenu(560, 248))
def s_captcha(th):
    stat = ['ready','warn','ready','warn','ready','meta','fail','queued','warn','ready','queued','busy']
    rows = P[:12]
    bar = f'<div class="notice warn" style="margin:8px 10px 6px;border-radius:var(--r-sm)"><span class="ico">{I["alert"]}</span><span class="msg"><b>出版社要求验证，请在 Chrome 里完成后点继续。</b> <span class="quiet">ScienceDirect 的 3 篇已暂停。</span></span><a class="btn sm" style="margin-left:auto">{I["chrome"]}打开 Chrome</a><a class="btn sm primary">继续</a></div>'
    tip = f'<div class="confirm" style="position:absolute;left:24px;top:334px;width:300px;padding:10px 12px;z-index:6"><b class="small" style="color:var(--error)">获取失败 · 需要机构登录</b><p class="micro quiet" style="margin:2px 0 0">在 Chrome 里登录学校账号后，右键「获取全文」重试。这篇在文献库里仍显示为「仅元数据」。</p></div>'
    mid = toolbar('本批 12 篇') + bar + table(rows=rows, stat=stat, focus=None) + tip
    right = rtabs() + f'<div class="rbody">{info_pane(P[1], "meta")}{vnav()}</div>'
    sb = statusbar(f'{I["pause"]}<b>正在获取全文 5/12</b><span class="prog"><i style="width:42%"></i></span><span class="small" style="color:var(--warn)">等待验证 3</span><span class="small" style="color:var(--error)">获取失败 1</span><span class="sbtn">取消</span>',
                   f'{I["route"]}<span>实验室台式机离线，已改用本机</span>')
    page('05-captcha-bar', th, win3(tabs(), tree(), mid, right, sb))
PRESETS = [('abs', '总结摘要', '每篇 3 句话 + 关键结论'), ('compare', '比较方法', '对比实验条件与方法'), ('table', '提取参数', '把关键参数整理成表'), ('dots', '更多…', '研究空白、综述草稿…')]
def preset_cards():
    return '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">' + ''.join(f'<div class="pcard"><b>{I[ic]}{t}</b><span>{d}</span></div>' for ic, t, d in PRESETS) + '</div>'
def inbox(chips, ph='问 mdtero AI，或点上面的任务…'):
    cs = ''.join(f'<span class="chip">{I["doc"]}<span>{e(c)}</span>{I["x"]}</span>' for c in chips)
    return f'<div class="inbox"><div style="display:flex;gap:5px;flex-wrap:wrap">{cs}</div><div class="ph">{ph}</div><div class="f"><span>{I["spark"]}</span><span>mdtero AI · 今日还可用 38 次（示例）</span><span class="send">{I["send"]}</span></div></div>'
def short(t, n=22): return t if len(t) <= n else t[:n].rstrip() + '…'
def s_aipane(th):
    sel = (2, 3, 4)
    mid = toolbar() + table(sel=sel)
    chips = [short(P[i]['t'], 18) for i in sel]
    stream = f'''<div style="display:flex;flex-direction:column;gap:8px;margin-top:12px"><div class="msg-u">比较这 3 篇的制备方法</div>
<div class="step"><div class="h"><span class="ok-c">{I["check"]}</span>读取 3 篇全文<span class="t">2 秒</span></div></div>
<div class="step"><div class="h"><span class="ok-c">{I["check"]}</span>找出各篇的方法段落<span class="t">{I["up"]}</span></div><div class="b">§2.1 浸渍法 · §2.2 真空浸渍 · §3 溶胶–凝胶</div></div>
<div class="step"><div class="h"><span class="spin acc-c"></span>整理成对比表…<span class="t">{I["down"]}</span></div></div></div>'''
    right = rtabs(ai=True, n=3) + f'<div class="rbody"><div class="rcont" style="display:flex;flex-direction:column;padding:12px 14px"><div class="micro quiet" style="margin-bottom:8px">选中的 3 篇会作为上下文。一键任务：</div>{preset_cards()}{stream}<div style="flex:1"></div>{inbox(chips)}</div></div>'
    page('06-ai-pane', th, win3(tabs(), tree(), mid, right))
def s_research(th):
    sel = P[2:5]
    papers = ''.join(f'<div class="pcard" style="margin-bottom:8px"><b style="font-size:12.5px;line-height:17px;display:block;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{e(p["t"])}</b><span>{e(p["v"])} · {p["y"]}</span><span style="margin-top:4px">{pill("ready")}</span></div>' for p in sel)
    left = f'<aside class="lp" style="padding:12px"><div class="stitle" style="font-size:13px">这次研究的文献 · 3</div><p class="micro quiet" style="margin:0 0 10px">从文献库拖进来，或在列表里多选后点「用 AI 研究」。</p>{papers}<a class="btn sm block" style="margin-top:4px">{I["plus"]}添加文献</a></aside>'
    chat = f'''<main class="mp" style="padding:14px 18px;display:flex;flex-direction:column;gap:10px"><div class="micro quiet">研究：方法对比 · 今天 17:42</div>
<div class="msg-u">比较这 3 篇的制备方法，整理成表，并指出各自的不足。</div>
<div class="step"><div class="h"><span class="ok-c">{I["check"]}</span>读取 3 篇全文<span class="t">2 秒</span></div></div>
<div class="step"><div class="h"><span class="ok-c">{I["check"]}</span>找出各篇的方法段落<span class="t">{I["down"]}</span></div></div>
<div class="step"><div class="h"><span class="ok-c">{I["check"]}</span>生成对比表和小结<span class="t">{I["down"]}</span></div></div>
<div style="font-size:13px;line-height:21px">已经写好「方法对比.md」，放在右边。三篇都用浸渍法把盐载入多孔基体，差别主要在真空处理和干燥温度；第 3 篇没有报告循环次数。<sup style="color:var(--accent)">§2.1</sup></div>
<div style="display:flex;gap:6px;flex-wrap:wrap"><span class="chip">接着：列出研究空白</span><span class="chip">接着：写一段综述</span></div>
<div style="flex:1"></div>{inbox([short(p["t"], 16) for p in sel], '继续问，比如「哪篇的循环稳定性最好？」')}</main>'''
    doc = f'''<aside class="rp"><div class="rtabs"><b style="font-size:13px">{I["doc"]} 方法对比.md</b><span class="badge acc">未保存</span><span style="margin-left:auto" class="micro quiet">Markdown</span></div>
<div class="rcont md" style="padding:6px 18px 0"><h3>方法对比</h3><table><tr><th>文献</th><th>载入方式</th><th>干燥</th><th>循环</th></tr><tr><td>[1]</td><td>浸渍</td><td>120 °C</td><td>20 次</td></tr><tr><td>[2]</td><td>真空浸渍</td><td>150 °C</td><td>50 次</td></tr><tr><td>[3]</td><td>溶胶–凝胶</td><td>80 °C</td><td>未报告</td></tr></table>
<h3>小结</h3><ul><li>真空浸渍载盐量更高，但工序更长。<sup>[2] §2.2</sup></li><li>干燥温度影响盐的分布和团聚。<sup>[1] §3.1</sup></li><li>[3] 缺少长期循环数据，结论需谨慎。</li></ul><p class="micro quiet">示例内容，实际由 mdtero AI 根据全文生成，每条都标出处。</p></div>
<div class="confirm" style="position:absolute;left:12px;right:12px;width:auto;bottom:64px"><h2 style="font-size:14px;margin:0 0 4px">存入文献库？</h2><p class="small quiet" style="margin:0">「方法对比.md」会作为笔记，挂在这 3 篇文献下面。</p><div class="acts"><a class="btn sm">取消</a><a class="btn sm primary">存入</a></div></div>
<div style="height:52px;flex:none;border-top:1px solid var(--line);display:flex;align-items:center;gap:8px;padding:0 12px"><a class="btn sm">{I["edit"]}编辑</a><a class="btn sm">{I["export"]}导出 .md</a><a class="btn sm primary" style="margin-left:auto">存入文献库…</a></div></aside>'''
    body = tabs([('ai', '研究：方法对比')], on=1) + f'<div class="panes" style="grid-template-columns:250px minmax(0,1fr) 440px">{left}{chat}{doc}</div>'
    page('07-research-tab', th, body)
def s_reader(th):
    p = P[16] if len(P) > 16 else P[0]
    title = 'Parameter control in synthesis of Vermiculite-CaCl2 composite materials for thermochemical heat storage'
    head = f'<link rel="stylesheet" href="file://{KX}katex.min.css"><script src="file://{KX}katex.min.js"></script>'
    script = r'''<script>document.querySelectorAll('[data-tex]').forEach(n=>katex.render(n.dataset.tex,n,{displayMode:true,throwOnError:false}))</script>'''
    read = f'''<main class="mp" style="overflow:hidden"><div class="tb"><a class="btn sm quiet">{I["lib"]}文献库</a><span class="quiet">{I["chev"]}</span><span class="small quiet">阅读</span><a class="btn sm quiet" style="margin-left:auto">目录</a><a class="btn sm quiet">在文中查找</a><a class="btn sm primary">{I["spark"]}用 mdtero AI 研究这篇</a></div>
<div style="padding:22px 44px;max-width:780px"><h1 style="font-size:22px;line-height:30px;margin:0 0 8px">{title}</h1>
<div class="small quiet">示例作者 A, 示例作者 B 等 · Energy · 2024 · 10.1016/j.energy.2024.130517（示例）</div>
<div style="display:flex;gap:10px;align-items:center;margin:10px 0 16px;padding-bottom:14px;border-bottom:1px solid var(--line)">{pill("ready")}<span class="micro quiet">来源：出版社 XML · 经由：实验室台式机</span></div>
<h2 style="font-size:16px">2 理论基础</h2><p style="font-size:14.5px;line-height:25px">盐水合物的吸附储热依靠可逆的水合与脱水反应。以氯化钙为例，反应可以写成：</p>
<div data-tex="\\mathrm{{CaCl_2\\cdot 2H_2O_{{(s)}}}} + 4\\,\\mathrm{{H_2O_{{(g)}}}} \\rightleftharpoons \\mathrm{{CaCl_2\\cdot 6H_2O_{{(s)}}}} + \\Delta H"></div>
<p style="font-size:14.5px;line-height:25px">平衡时的水蒸气分压与温度满足 Van 't Hoff 关系：</p><div data-tex="\\ln\\frac{{p_{{eq}}}}{{p^\\circ}} = -\\frac{{\\Delta H^\\circ}}{{RT}} + \\frac{{\\Delta S^\\circ}}{{R}}"></div>
<p style="font-size:14.5px;line-height:25px">本节其余内容为设计稿占位文字，用来展示正文排版、行距和公式渲染效果。</p></div></main>'''
    md = '''<div class="md" style="margin-top:10px"><div class="step"><div class="h"><span class="ok-c">''' + I['check'] + '''</span>已读完全文<span class="t">14 秒</span></div></div><h3>摘要总结</h3><ul><li><b>研究问题：</b>怎样控制蛭石–氯化钙复合材料的合成参数，让储热密度和循环稳定性兼顾。<sup>§1</sup></li><li><b>方法：</b>改变浸渍浓度和干燥温度，对比吸附量与循环表现。<sup>§3</sup></li><li><b>结论：</b>示例占位，实际由 mdtero AI 根据全文生成，每条标出处。<sup>§4</sup></li></ul></div>'''
    right = rtabs(ai=True, n=1) + f'''<div class="rbody"><div class="rcont" style="display:flex;flex-direction:column;padding:12px 14px"><div style="display:flex;gap:6px;flex-wrap:wrap"><span class="chip" style="background:var(--accent);color:var(--on-accent)">总结摘要</span><span class="chip">比较方法</span><span class="chip">提取参数</span><span class="chip">更多…</span></div>{md}
<div style="display:flex;gap:6px;margin-top:10px"><a class="btn sm">{I["edit"]}编辑</a><a class="btn sm">{I["export"]}导出 .md</a><a class="btn sm primary" style="margin-left:auto">存入文献库…</a></div><div style="flex:1"></div>{inbox([short(title, 20)], '追问这篇，比如「干燥温度怎么选？」')}</div></div>'''
    body = tabs([('doc', short(title, 26))], on=1) + f'<div class="panes" style="grid-template-columns:minmax(0,1fr) 380px">{read}<aside class="rp">{right}</aside></div>'
    page('08-reader-ai', th, body, head, script)
def s_tour(th):
    cards = ''
    for i, p in enumerate(P[8:12]):
        b = '<a class="btn sm primary" id="add">加入文献库</a>' if i == 0 else '<a class="btn sm">加入文献库</a>'
        cards += f'<div style="padding:12px 16px;border-bottom:1px solid var(--line)"><b style="display:block;font-size:13.5px;line-height:20px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{e(p["t"])}</b><div class="micro quiet" style="margin:2px 0 8px">{e(p["v"])} · {p["y"]} · 被引 {p["c"]} · {e(p["d"])}</div><div style="display:flex;gap:6px">{b}<a class="btn sm quiet">看引文网络</a></div></div>'
    mid = toolbar(q='salt hydrate thermochemical', scope='在线检索') + f'<div class="micro quiet" style="padding:8px 16px 0">约 3,987 篇 · 只是题录信息，加入文献库后才能获取全文</div>{cards}'
    over = f'''<div class="spot" id="spot"></div>
<div class="confirm" id="cf" style="position:absolute;z-index:6"><h2 style="font-size:14px;margin:0 0 4px">存入文献库？</h2><p class="small quiet" style="margin:0 0 4px">将加入「我的文献库」：</p><p class="small" style="margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{e(P[8]["t"])}</p><p class="micro quiet" style="margin:4px 0 0">只存题录信息，全文之后可以右键获取。</p><div class="acts"><a class="btn sm">取消</a><a class="btn sm primary">存入</a></div></div>
<div class="tour left" id="tr" style="z-index:6"><b>第 2 步：加入文献库</b>点「加入文献库」，确认后这篇才会存进去。不确认就不会写入。<div class="row"><span class="dots"><i></i><i class="on"></i><i></i></span><span style="display:flex;gap:12px;align-items:center"><span class="skip">跳过教程</span><span class="next">下一步</span></span></div></div>'''
    script = '<script>const r=document.getElementById("add").getBoundingClientRect(),s=document.getElementById("spot");Object.assign(s.style,{left:(r.left-4)+"px",top:(r.top-4)+"px",width:(r.width+8)+"px",height:(r.height+8)+"px",zIndex:5});const c=document.getElementById("cf");Object.assign(c.style,{left:(r.left)+"px",top:(r.bottom+10)+"px"});const t=document.getElementById("tr");Object.assign(t.style,{left:(r.left+352)+"px",top:(r.bottom+10)+"px"})</script>'
    page('09-tour-step2', th, win3(tabs(), tree(counts=(0, 0), empty=True), mid, rtabs() + f'<div class="rbody">{empty_info()}</div>') + over, '', script)
SNAV = [('general', 'gear', '通用'), ('account', 'user', '账号'), ('ai', 'spark', 'mdtero AI'), ('route', 'route', '全文出口'), ('adv', 'bolt', '高级'), ('about', 'info', '关于')]
def settings(on, content):
    nav = ''.join(f'<div class="ti{" on" if k == on else ""}">{I[ic]}<span>{t}</span></div>' for k, ic, t in SNAV)
    return f'<div class="swin"><div class="lights" style="z-index:2"><i></i><i></i><i></i></div><div style="position:absolute;top:12px;left:0;right:0;text-align:center;font-size:12px;font-weight:600;color:var(--quiet)">设置</div><nav class="snav">{nav}</nav><div class="sbody">{content}</div></div>'
def srow(ic, name, sub, right, badge=''):
    return f'<div class="srow">{ic}<div class="lbl"><span style="font-weight:600">{name}{badge}</span><small>{sub}</small></div><div class="rt">{right}</div></div>'
def s_set_account(th):
    c = f'''<h1>账号</h1><p class="small quiet" style="margin:0 0 18px">登录后，文献库会同步到你的 mdtero 账号。</p>
<div class="sec">{srow('<span class="acct" style="border:0;padding:0;height:auto"><span class="av" style="width:40px;height:40px;font-size:16px">J</span></span>', 'Jianbin', 'jianbin@example.edu（示例）· 已同步 2 分钟前', '<a class="btn sm">在浏览器管理账号</a><a class="btn sm quiet">退出登录</a>')}</div>
<div class="stitle">同步</div><div class="sec">{srow('', '自动同步文献库', '题录、分类、标签和笔记。全文按需在每台电脑上获取。', '<span class="sw"></span>')}{srow('', '立即同步', '上次同步：今天 17:38', '<a class="btn sm">立即同步</a>')}</div>
<div class="stitle">用量</div><div class="sec">{srow('', 'mdtero AI', '今日还可用 38 次（示例）· 每天 0 点重置', '<span class="prog" style="width:140px"><i style="width:24%"></i></span>')}</div>'''
    page('10-settings-account', th, settings('account', c))
def s_set_ai(th):
    exp = '<span class="badge exp">实验</span>'
    rows = (srow('<span class="pic">OR</span>', 'OpenRouter', '<span class="dot ok"></span> 已连接 · deepseek/deepseek-chat（示例）', '<span class="radio"></span><a class="btn sm">换模型</a><a class="btn sm quiet">断开</a>') +
            srow('<span class="pic">GH</span>', 'GitHub Copilot', '在浏览器打开的页面输入代码 <span class="kbd">WDJB-MJHT</span> · 等待授权…', '<a class="btn sm">复制代码</a><a class="btn sm quiet">取消</a>') +
            srow('<span class="pic">GP</span>', 'ChatGPT 订阅', '用你的 ChatGPT Plus / Pro 账号', '<a class="btn sm">连接…</a>', exp) +
            srow('<span class="pic">CL</span>', 'Claude 订阅', '用你的 Claude Pro / Max 账号', '<a class="btn sm">连接…</a>', exp))
    c = f'''<h1>mdtero AI</h1><p class="small quiet" style="margin:0 0 18px">读论文、写总结时用哪个模型。默认就能用，不用填任何密钥。</p>
<div class="sec">{srow(f'<span class="pic acc">{I["spark"]}</span>', 'mdtero AI', '内置，无需设置 · 今日还可用 38 次（示例）', '<span class="radio on"></span><span class="small quiet">默认</span>', '<span class="badge ok">正在使用</span>')}</div>
<div class="stitle">用自己的账号</div><p class="sdesc">连接后可以在右侧 mdtero AI 里切换。登录在系统浏览器里完成，不需要粘贴密钥。</p><div class="sec">{rows}</div>
<p class="micro quiet" style="max-width:720px;margin:0">登录凭据只保存在这台电脑的系统钥匙串里，不会上传到 mdtero。标「实验」的方式可能随时不可用。</p>'''
    page('11-settings-ai', th, settings('ai', c))
def s_set_route(th):
    rows = (srow('<span class="radio on"></span>', '自动', '先用本机；不行时按顺序换到你的其他设备', '<span class="badge acc">默认</span>') +
            srow('<span class="radio"></span>', '本机直连', '这台电脑', '') +
            srow('<span class="radio"></span>', f'{I["monitor"]} 实验室台式机', '<span class="dot off"></span> 离线 · 12 分钟前在线', '<a class="btn sm quiet">重命名</a><a class="btn sm quiet">移除</a>') +
            srow('<span class="radio"></span>', f'{I["monitor"]} 家里电脑', '<span class="dot ok"></span> 在线 · 延迟 48 ms', '<a class="btn sm quiet">重命名</a><a class="btn sm quiet">移除</a>'))
    c = f'''<h1>全文出口</h1><p class="small quiet" style="margin:0 0 18px">获取出版社全文时从哪台电脑的网络出去。只用于出版社全文，别的流量不经过这里。</p>
<div class="sec">{rows}</div><div style="display:flex;gap:10px;align-items:center;max-width:720px"><a class="btn">{I["plus"]}添加出口…</a><span class="small quiet">在要添加的电脑上打开 mdtero，输入配对码即可。</span></div>
<div class="notice info" style="max-width:720px;margin-top:18px"><span>{I["shield"]}</span><span class="msg">只能添加你自己的设备，仅供你的账号使用。设备离线时会自动改用下一个，并在窗口底部提示。</span></div>'''
    page('12-settings-route', th, settings('route', c))
def s_set_adv(th):
    c = f'''<h1>高级</h1><p class="small quiet" style="margin:0 0 18px">一般不需要改。遇到问题时可以看这里的状态。</p>
<div class="stitle">连接状态</div><div class="sec">{srow(f'<span class="pic">{I["chrome"]}</span>', 'Chrome 连接', '<span class="dot ok"></span> 已连接 · Chrome 130（示例）', '<a class="btn sm">重新连接</a>')}{srow(f'<span class="pic">{I["route"]}</span>', '当前全文出口', '自动 → 本机直连', '<a class="btn sm quiet">去设置</a>')}</div>
<div class="stitle">获取全文</div><div class="sec">{srow('', '同一出版社请求间隔', '3–5 秒随机，避免被出版社限制', '<span class="small quiet">固定</span>')}{srow('', '连续失败 3 次自动暂停该出版社', '其他出版社照常获取', '<span class="sw"></span>')}{srow('', '重启后询问是否继续没取完的', '', '<span class="sw"></span>')}</div>
<div class="stitle">问题反馈</div><div class="sec">{srow('', '导出诊断信息', '只包含状态和错误编号，不含文献内容和账号密码', '<a class="btn sm">导出…</a>')}</div>'''
    page('13-settings-advanced', th, settings('adv', c))
def s_set_about(th):
    c = f'''<div style="display:flex;align-items:center;gap:16px;margin:10px 0 24px"><img src="{LOGO}" style="width:64px;height:64px" alt="mdtero"><div><h1 style="margin:0">mdtero</h1><div class="small quiet">0.1.0 内测版 · 0.1.0 Beta</div></div></div>
<div class="sec">{srow('', '检查更新', '已是最新版本', '<a class="btn sm">检查更新</a>')}{srow('', '开源许可', '本软件使用的开源组件及其许可证（THIRD_PARTY_NOTICES）', '<a class="btn sm">查看</a>')}{srow('', '隐私与条款', '', '<a class="btn sm quiet">在浏览器打开</a>')}{srow('', '帮助与教程', '重新打开入门教程', '<a class="btn sm">打开教程</a>')}</div>'''
    page('14-settings-about', th, settings('about', c))
SCREENS = [s_login, s_welcome, s_import, s_library, s_captcha, s_aipane, s_research, s_reader, s_tour, s_set_account, s_set_ai, s_set_route, s_set_adv, s_set_about]
async def shoot(only=None):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for f in sorted(H.glob('*.html')):
            if only and not any(f.stem.startswith(o) for o in only): continue
            th = 'dark' if f.stem.endswith('dark') else 'light'
            ctx = await b.new_context(viewport={'width':1280,'height':800}, color_scheme=th, device_scale_factor=1)
            pg = await ctx.new_page(); await pg.goto('file://'+str(f)); await pg.wait_for_timeout(350)
            await pg.screenshot(path=str(M/(f.stem+'.png'))); await ctx.close()
        await b.close()
if __name__ == '__main__':
    import sys
    for f in H.glob('*.html'): f.unlink()
    for th in ('light','dark'):
        for s in SCREENS: s(th)
    asyncio.run(shoot()); print('done', len(list(H.glob('*.html'))))
