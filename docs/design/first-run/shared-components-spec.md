# mdtero 共享组件库规格（doi2md/contracts/）

> 状态：设计稿，待工程评审。日期：2026-10-23。
>
> 用于以下几处：
> - 桌面客户端（doi2md `connect/`，Tauri）
> - 后端 MCP 页面（mdtero-backend `service/mcp_ui/`，版本 5be33ce）
> - 官网和 PWA（Nextmdtero，版本 7a5241f）
>
> 配套文件：
> - `/workspace/mdtero-tokens.css`：设计变量的唯一来源
> - `/workspace/first-run/components.css`：组件 CSS 草案
> - `/workspace/first-run/mcp-reskin/mcp-reskin.css`：MCP 页面换肤用的变量映射
>
> 建议的仓库布局：
> - `doi2md/contracts/ui/tokens.css`
> - `doi2md/contracts/ui/components.css`
> - `doi2md/contracts/ui/brand-mark.svg`
> - `doi2md/contracts/ui/README.md`（这份文档）
>
> 客户端和 MCP 页面都在构建时把这几份文件复制或 vendoring 进去，不能各自修改。

## 1. 原则

1. **颜色、字号、圆角、间距全部用 token。**
   - 组件 CSS 里不写十六进制色值。只有一个例外：遮罩可以用 `rgba(28,22,18,.34)`，但它也要登记成 `--scrim`。
2. **浅色和深色是同一套 class。**
   - 深色模式只覆盖 token，不另写组件。
   - 切换方式：`prefers-color-scheme`、`html.dark` 或 `[data-theme=dark]`，三者都要支持。
3. **状态不能只靠颜色表示。** 胶囊、图标和提示条都要同时有颜色、图形和文字。
4. **置灰而不隐藏。**
   - disabled 状态用 `opacity: var(--disabled-opacity)`（.52）加 `aria-disabled`，并用 title 写明原因。
5. **焦点环统一**，用 `box-shadow: var(--focus-ring)`（3px `--focus` 的 35%）。
6. **品牌名一律小写 mdtero，界面里不出现内部用词。**
   - 内部用词包括：Connect、relay、Pi、worker、R2、MCP 客户端、curl、PDF（来源行除外）、VPN、模型名。

## 2. Token 一览

取值以 `mdtero-tokens.css` 为准。

| 类别 | Token | 浅色 | 深色 |
|---|---|---|---|
| 背景 | `--bg` | #f4f2ef | #1c1f1e |
| 卡片和表面 | `--surface` | #fdfcfb | #242827 |
| 浅底（侧栏、输入框、斑马纹） | `--muted`，在 MCP 里改名为 `--tk-muted`，见 §5.3 | #f8f7f5 | #2b2f2e |
| 正文 | `--ink` | #2c302e | #ece9e4 |
| 次要文字 | `--quiet` | #626965 | #a3a8a5 |
| 线 | `--line` | rgba(60,47,36,.12) | 深色值见 tokens 文件 |
| 主色 | `--accent` | #a3542f | #d0784f |
| 主色悬停，品牌深色 | `--accent-hover` / `--brand` | #6d3920 | 深色值见 tokens 文件 |
| 主色浅底 | `--accent-soft` | #f6e9e0 | #4a3226 |
| 主色文字 | `--accent-ink` | #6d3920 | #f0b48f |
| 主色上的文字 | `--on-accent` | #fff | #1c1f1e |
| 语义色 | `--ok` / `--warn` / `--error` | #206e56 / #895714 / #923d32 | 深色值见 tokens 文件 |
| 焦点 | `--focus` | #a36948 | 深色值见 tokens 文件 |
| 字号 | `--fs-display` / `--fs-title` / `--fs-body` / `--fs-small` / `--fs-micro` | 26 / 17 / 14 / 12 / 11 | — |
| 间距 | `--s1`…`--s6` | 4 / 8 / 12 / 16 / 24 / 32 | — |
| 圆角 | `--r-sm` / `--r-md` / `--r-lg` | 8 / 12 / 14 | — |
| 其他 | `--sidebar-w` 230、`--focus-ring`、`--disabled-opacity` .52、`--shadow-pop` | | |

- 字体统一用 Inter，中文回退到系统黑体（PingFang SC / Microsoft YaHei / Noto Sans CJK SC）。
- 数字用 `font-variant-numeric: tabular-nums`。

**新建议补充的 token**：
- `--scrim`：遮罩色
- `--table-fs`：表格字号，12.5，桌面版的密集表格专用
- `--row-h`：表格行高，28
- `--tag-1`…`--tag-6`：彩色标签。直接引用语义色和主色，不新增色相。

## 3. 组件

> 尺寸单位都是 px。「MCP 来源」一栏写明这个组件是从 MCP UI 的哪个 class 来的，换肤时保持这个对应关系。

### 3.1 基础组件

| 组件 | Class | 尺寸 | 状态 | MCP 来源 |
|---|---|---|---|---|
| 按钮 | `.btn` + `.sm` / `.lg` / `.primary` / `.quiet` / `.text` / `.danger` / `.block` | 高 28 / 36 / 44，左右内边距 10 / 14 / 18，圆角 `--r-sm`，字重 560 | 默认、悬停、按下（下移 1px）、焦点、置灰、加载中（`.spin` 加上文字） | `.primary-button`、`.quiet-accent`、`.ghost-button`、`.danger-button` |
| 输入框 | `.input`，外面套 `.field` | 高 36，圆角 `--r-sm`，底色 `--muted` | 焦点时描边 `--accent` 并显示焦点环；错误时描边 `--error`，下方 micro 字号写错误说明 | `.search-box input`、`.field` |
| 选择卡片 | `.choice` | 宽 290–360，内边距 24，圆角 `--r-lg` | 悬停（描边 `--accent` 加阴影）、焦点、选中 | `.intake-option` |
| 卡片和分区 | `.card` / `.sec` | 内边距 16 或 0 14，圆角 `--r-md` | — | `.sheet-card`、`.status-grid article` |
| 设置行 | `.srow` | 上下内边距 13，图标 28，右侧放按钮 | 置灰 | settings.html 里的设备行（DeviceRow） |
| 状态胶囊 | `.pill` + `.ready` / `.meta` / `.queued` / `.busy` / `.fail` / `.warn` | 高 22，左右内边距 8，圆角 999，字号 11.5，前面带 6px 圆点或转圈 | — | `.status-pill` |
| 徽标 | `.badge` + `.exp` / `.ok` / `.acc` | 高 18，字号 10.5，字重 650 | — | — |
| 标签 chip | `.chip` | 高 24，最宽 132，后面带 × | 悬停、可移除 | `.tag-filter-pill`、`.context-chip` |
| 快捷键和代码 | `.kbd` | 高 20，等宽字体，底色 `--muted` | — | — |
| 开关 | `.sw` | 30×18 | 开、关、置灰 | settings 里的 toggle |
| 单选框 | `.radio` | 16，选中时内圈 8 | 选中、焦点 | — |
| 头像 | `.avatar` / `.av` | 28 / 40，底色 `--accent-soft`，文字 `--accent-ink` | — | — |
| 状态圆点 | `.dot` + `.ok` / `.off` / `.warn` | 7 | — | `.connection-dot` |

### 3.2 反馈组件

| 组件 | Class | 规格 | MCP 来源 |
|---|---|---|---|
| 提示条 | `.notice` + `.info` / `.warn` / `.error` / `.ok` | 最小高 40，内边距 10 12，圆角 `--r-md`。底色是对应语义色的 12%，文字是对应语义色调深后的颜色。结构是：图标 → 一句白话说明 → 右侧 1–2 个 `.btn.sm`。验证码用 `.warn`，并加 `role="alert"` | `.connection-banner`、`.notice` |
| 确认卡片 | `.confirm` | 宽 300–380，圆角 `--r-lg`，阴影 `--shadow-pop`，有标题、说明和「取消」「主按钮」。Enter 等于主按钮，Esc 等于取消。破坏性操作用 `.danger` | `.confirm-card` |
| 弹层 | `.sheet` | 宽 560 / 900，圆角 `--r-lg`，下面垫 `--scrim` 遮罩。在宽度小于 700 时改成底部弹层，带 4×36 的拖拽条 | `.sheet`、`.sheet-card` |
| 引导气泡 | `.tour` + `.up` / `.left` | 宽 300，底色 `--ink`，文字 `--bg`，箭头 8，底部是进度点、跳过、下一步 | `.guide-num` 的编号样式 |
| 聚光圈 | `.spot` | `box-shadow: 0 0 0 3px var(--accent), 0 0 0 2400px rgba(20,16,12,.38)` | — |
| 进度条 | `.prog` | 高 4，圆角 999，底色 `--muted`，填充 `--accent` | `.quota-bar` |
| 转圈 | `.spin` | 12 或 14。开启 reduced-motion 时改成静态的「…」 | — |
| 空状态 | `.empty` | 图标块 40、标题 14/600、说明（small，`--quiet`），可以带一个按钮 | `.nav-empty` |
| 骨架屏 | `.skel` | 底色 `--muted`，用 1.2s 的闪光动画（reduced-motion 时关闭） | — |

### 3.3 导航和布局组件

| 组件 | Class | 规格 |
|---|---|---|
| 标签条 | `.tabs` / `.tab` | 整条高 40，每个标签高 31，选中时 32，最宽 230，可以关闭（× 14）。标签可以拖动排序，中键点击关闭 |
| 三栏 | `.panes` | 230 \| 自适应 \| 352。分隔条可以拖动，宽 4（悬停时显示 `--accent` 的 30%） |
| 分类树 | `.tree` / `.ti` | 行高 26，每级缩进 14。右侧计数用 micro 字号。拖拽时，放置目标用 `--accent-soft` 底色加 1px `--accent` 描边 |
| 分段控件 | `.seg` | 高 32，内衬 3px，选中段用 `--surface` 底色加阴影。用 `role="tablist"` |
| 竖向分区导航 | `.vnav` | 宽 38，按钮 28 |
| 工具栏 | `.tb` | 高 46，按钮间距 6，竖分隔线高 20 |
| 搜索框 | `.srch` | 高 28，宽 214。前面是范围下拉，后面可以显示 `.kbd` 快捷键提示 |
| 表格 | `table.zt` | 见 first-run-spec §2.2 |
| 右键菜单 | `.menu` | 宽 248，项高 30，分组标题用 `.hd`，分隔线用 `.sep`。用 `role="menu"` |
| 状态栏 | `.sbar` | 高 30，字号 12，左边显示队列，右边显示一次性提示 |
| 账号行 | `.acct` | 高 48 |
| 设置窗口 | `.swin` / `.snav` / `.sbody` | 左侧导航 200，内容区最大宽 720 |

### 3.4 mdtero AI 组件

| 组件 | Class | 规格 | MCP 来源 |
|---|---|---|---|
| 任务卡片 | `.pcard` | 两列网格，间距 8，内边距 10 12，圆角 `--r-md`，图标 14，标题 13/600，说明用 micro 字号 | `.reader-ai-panel` 里的预设按钮 |
| 用户消息 | `.msg-u` | 右对齐，最宽 85%，底色 `--accent-soft`，圆角 12 12 4 12 | — |
| 步骤卡片 | `.step` | 高 30，可以折叠。左边是状态图标，右边是用时或 ▾，展开后用 micro 字号显示引用的段落 | — |
| 输入卡片 | `.inbox` | 固定在底部，圆角 `--r-lg`，阴影 `--shadow-pop`。有 chip 行、输入区（最少两行）、底部一行（次数和 30×30 的发送按钮） | `.reader-ai-panel textarea` |
| Markdown | `.md` | 正文 14.5/25，h2 15/650，表格用 1px `--line` 线、表头 `--muted` 底色，`§` 引用是 `--accent` 色的上标，公式用 KaTeX | `.markdown` |

## 4. Logo

**唯一来源**：Nextmdtero `public/assets/brand-mark.svg`。它和 `src/app/components/MdteroLogo.tsx` 是同一个图形，已经复制到 `/workspace/first-run/assets/brand-mark.svg`。

图形构成：
- 256 的 viewBox。
- 圆角方块：rx 62，渐变 #F6E6D5 → #E2B792。
- 内描边：#FFF8F1，不透明度 .72。
- 「M」字形：渐变 #6D3920 → #2F1A12。

**以后各处都只用这一个 logo**，包括：
- 客户端：标签条、登录卡片、关于页
- MCP 页面：登录、授权、设置、工作区
- 安装包和应用图标
- 官网和 PWA 的 manifest 图标

下面两个旧版本作废：
- doi2md `connect/app/index.html` 里的 `.brand-icon`，一个文字「M」；
- MCP 的 `.mark`，Georgia 字体的「M」，或者内联 svg。

**尺寸**：

| 尺寸 | 用在哪里 |
|---|---|
| 16 | 标签条、favicon |
| 20 | 菜单、紧凑的页头 |
| 28 | 页头、MCP masthead |
| 36 | 登录卡片 |
| 48 / 64 | 关于页、空状态 |
| 应用图标 | 从 SVG 导出 32 / 128 / 256 / 512 / 1024 的 png、icns、ico，替换 `connect/native/src-tauri/icons/*` |

**留白**：四周至少留出图形边长的 1/4，比如 28px 的图形四周留 7px。和文字并排时，间距 8–10，文字垂直居中。

**浅色和深色**：两种模式都直接用原图。它自带浅色底块，在深色背景上也能看清。
- 不改颜色、不拉伸、不加阴影、不描边、不旋转。
- 不要放在 `--accent` 色的实心底上。

**文字标识**：
- logo 旁边的文字一律是小写「mdtero」，字重 650，颜色 `--ink`。
- 「M」字形本身是图形的一部分，不受小写规则约束。
- 官网页头现在用 CSS 把文字变成了大写的「Mdtero」，和这条规则冲突，需要官网改成小写。**已定（10/23）**：已交给工程主管排进网站修复。

**对应的 class**：`.logo`（容器）和 `.logo-mark`（img，28；`.lg` 为 48）。

## 5. MCP 页面换肤（统一成砖红主色）

### 5.1 范围

现状（mdtero-backend 版本 5be33ce）：

| 页面 | 文件 | 现在的样子 |
|---|---|---|
| 登录、授权页 | `service/mcp_ui/auth_chrome.css`，由 `service/mcp_oauth.py` 和 `routes/mcp_connect.py` 输出 | `--accent:#2f4a3a` 深绿；`.mark` 是 Georgia 字体的「M」 |
| 设置页 | `service/mcp_ui/settings.html`，样式内联 | 同样是深绿 `#2f4a3a` 加 Georgia |
| 工作区和阅读器 | `service/mcp_ui/web/reader.css`、`web/reader.html`，构建产物是 `mcp_ui/reader.html` | `--accent:#455d99` 蓝色，`--accent-soft:#edf1fb`；文章正文用 Georgia 衬线体；13px 系统字体 |

对照图在 `/workspace/first-run/mcp-ref/`：r1-library、r2-inspector、r3-reader、r4-settings，各有浅色和深色。另外还有 `/workspace/component-inventory/04–08`。

### 5.2 做法

1. 先引入 `contracts/ui/tokens.css`，再引入 `mcp-reskin.css`。这份文件只改变量和少量写死的颜色，不改布局。
2. 变量映射，浅色和 `html.dark, html[data-theme=dark]` 都要有：

| MCP 变量 | 改成 |
|---|---|
| `--bg` | `var(--surface)` |
| `--soft` | `var(--tk-muted)` |
| `--ink` | `var(--ink)` |
| `--muted`（在 MCP 里是**次要文字**） | `var(--quiet)` |
| `--line` | `var(--line)` |
| `--accent`（原来 #455d99 或 #2f4a3a） | `var(--accent)` |
| `--accent-soft` | `var(--accent-soft)` |
| `--green` | `var(--ok)` |
| `--danger` | `var(--error)` |
| `--font` 和 `--serif` | Inter 字体栈 |

3. 写死的颜色要改掉：
   - `.primary-button` 的白字改成 `var(--on-accent)`；
   - `.sheet` 的遮罩改成 `var(--scrim)`；
   - 原来的焦点 outline 改成 `var(--focus-ring)`；
   - settings.html 里内联的 #2f4a3a 全部删掉，改为引用 tokens。
4. logo：`.mark` 里原来的 Georgia「M」或内联 svg，换成 `<img src="brand-mark.svg" width="28">`。也可以用 CSS 的 `--logo-url` 背景图，mcp-reskin.css 里已经写好。
5. 字体和字号：
   - Georgia 全部换成 Inter；
   - 阅读器 `.markdown` 正文 15px；
   - 界面基础字号从 13 调到 `--fs-body` 14（桌面表格单独用 12.5）。
6. 文献列表的状态列从原来的宽度扩到 84px，放得下「全文已就绪」胶囊。

### 5.3 命名冲突（必须处理）

**改名为 `--tk-muted` 已获产品经理同意（10/23）。**

MCP 的 `--muted` 指**次要文字颜色**，而 tokens 的 `--muted` 指**浅底色**。两者同名，意思不同。

处理方式：
- 在 MCP 页面里，tokens 的浅底色改名为 `--tk-muted`，`--bg` 同理改名为 `--tk-bg`。这一步已经在 `mcp-reskin/mx.css` 里演示过。
- MCP 原来的 `--muted` 映射到 `--quiet`。
- 下一个大版本里，统一把 MCP 源码中的 `var(--muted)` 改成 `var(--quiet)`，然后去掉别名。

### 5.4 验收

- [ ] 把 MCP 的登录、授权、设置、工作区（文献库和阅读器）页面，和客户端的对应页面并排截图，**看起来像同一个产品**，要满足这几条：
  - 主色是同一个砖红；
  - logo 是同一个；
  - 字体都是 Inter；
  - 按钮、胶囊、卡片的圆角和高度一致；
  - 浅色和深色都满足。
- [ ] 换肤后，MCP 页面里搜不到 `#2f4a3a`、`#455d99`、`#edf1fb` 和 `Georgia`。
- [ ] `tests/mcp_ui/host.html` 宿主在 `?theme=dark` 下渲染，没有对比度问题。
- [ ] MCP 页面的布局和交互不变，回归测试 `tests/mcp_ui` 全部通过。

## 6. 客户端旧界面要替换的地方（doi2md 版本 f4e286e）

- `connect/app/index.html`：`.brand-icon` 的文字「M」换成 brand-mark.svg；所有写死的颜色换成 tokens。
- `connect/native/src-tauri/icons/*`：用 brand-mark.svg 重新生成，比如用 `tauri icon brand-mark-1024.png`。**产品经理 10/23 已同意。**
- 安装包的标题、关于页：写「mdtero 0.1.0 内测版」，并提供 THIRD_PARTY_NOTICES 入口。

## 7. 设计稿怎么生成

- 用 `/workspace/first-run/build3.py` 生成：先写出 HTML（`html3/`），再用 Playwright 截图成 1280×800 的 PNG（`mocks/`）。
- 页面直接引用 tokens 和 components.css，所以设计稿本身就是组件的活样例。
- 之前的 `build.py`（v1 顶栏布局）和 `build2.py`（往 MCP 页面里注入的方案）都已经作废，只留作参考。
