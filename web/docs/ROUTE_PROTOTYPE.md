# AskFlow 前端路由表与页面原型结构

## 1. 实现策略

理想路由仍然建议采用：

- `/login`
- `/register`
- `/app/chat`
- `/app/chat/:conversationId`
- `/app/tickets`
- `/app/tickets/:ticketId`
- `/admin/dashboard`
- `/admin/documents`
- `/admin/intents`

但考虑到当前后端仅提供静态资源挂载，没有前端路由回退，本轮页面骨架采用：

- `/static/index.html#/login`
- `/static/index.html#/register`
- `/static/index.html#/app/chat`
- `/static/index.html#/app/chat/:conversationId`
- `/static/index.html#/app/tickets`
- `/static/index.html#/app/tickets/:ticketId`
- `/static/index.html#/admin/dashboard`
- `/static/index.html#/admin/documents`
- `/static/index.html#/admin/intents`

这意味着：

- 文档中的业务路由是正式版目标
- 代码中的 hash 路由是当前可直接运行的原型方案

## 2. 前端路由表

| 业务路由 | 原型路由 | 页面 | 权限 | 主要接口 |
|------|------|------|------|------|
| `/login` | `#/login` | 登录页 | 公开 | `POST /api/v1/admin/auth/login` |
| `/register` | `#/register` | 注册页 | 公开 | `POST /api/v1/admin/auth/register` |
| `/app/chat` | `#/app/chat` | 智能问答工作台 | 登录用户 | `GET/POST /api/v1/chat/conversations`、`GET /messages`、`WS /api/v1/chat/ws/{token}` |
| `/app/chat/:conversationId` | `#/app/chat/:conversationId` | 指定会话页 | 登录用户 | 同上 |
| `/app/tickets` | `#/app/tickets` | 我的工单列表 | 登录用户 | `GET /api/v1/tickets` |
| `/app/tickets/:ticketId` | `#/app/tickets/:ticketId` | 工单详情 | 登录用户 | `GET /api/v1/tickets/{id}`、`PUT /api/v1/tickets/{id}` |
| `/admin/dashboard` | `#/admin/dashboard` | 数据看板 | agent/admin | `GET /api/v1/admin/analytics` |
| `/admin/documents` | `#/admin/documents` | 文档管理 | agent/admin | `GET /api/v1/admin/documents`、`POST /api/v1/embedding/documents` |
| `/admin/intents` | `#/admin/intents` | 意图配置 | agent/admin，写操作仅 admin | `GET /api/v1/admin/intents`、`POST/PUT /api/v1/admin/intents` |

## 3. 页面原型结构

### 3.1 登录页

```text
+------------------------------------------------------+
| AskFlow 品牌区                                       |
| 产品说明 / 系统卖点                                  |
|                                                      |
| 账号登录卡片                                         |
| - 用户名                                             |
| - 密码                                               |
| - 登录按钮                                           |
| - 错误提示                                           |
| - 去注册链接                                         |
+------------------------------------------------------+
```

关键状态：

- idle
- submitting
- success
- error

### 3.2 注册页

```text
+------------------------------------------------------+
| 欢迎加入 AskFlow                                     |
|                                                      |
| 注册卡片                                             |
| - 用户名                                             |
| - 邮箱                                               |
| - 密码                                               |
| - 确认密码                                           |
| - 注册按钮                                           |
| - 返回登录链接                                       |
+------------------------------------------------------+
```

关键状态：

- 表单校验
- 提交中
- 注册成功提示

### 3.3 应用主框架

```text
+------------------+-----------------------------------+
| 侧边导航         | 顶部条                            |
| - 智能问答       | - 当前页面标题                    |
| - 我的工单       | - 用户信息                        |
| - 管理菜单       | - 退出登录                        |
|                  +-----------------------------------+
|                  | 页面主内容区                      |
|                  |                                   |
|                  | 根据路由切换不同模块              |
+------------------+-----------------------------------+
```

公共组件：

- `AppSidebar`
- `Topbar`
- `NoticeBar`
- `EmptyState`
- `StatCard`
- `TableCard`
- `Drawer/Panel`

### 3.4 智能问答工作台

```text
+--------------------+--------------------------+------------------+
| 会话列表           | 聊天主区                 | 辅助信息栏       |
| - 新建会话         | - 会话标题               | - 当前会话状态   |
| - 会话项           | - 消息流                 | - 意图说明       |
|                    | - 来源引用               | - 快捷创建工单   |
|                    | - 输入框/发送/停止       | - 最近工单       |
+--------------------+--------------------------+------------------+
```

关键组件拆分：

- `ConversationSidebar`
- `MessageList`
- `Composer`
- `SourceChips`
- `IntentBadge`
- `TicketComposerPanel`

### 3.5 我的工单列表

```text
+------------------------------------------------------+
| 标题区 + 筛选区                                      |
| - 状态筛选                                           |
| - 刷新                                               |
|                                                      |
| 工单列表卡片                                         |
| - 标题 / 状态 / 优先级 / 时间 / 关联会话             |
| - 点击进入详情                                       |
+------------------------------------------------------+
```

### 3.6 工单详情

```text
+---------------------------------+--------------------+
| 工单主信息                      | 状态侧栏           |
| - 标题                          | - 当前状态         |
| - 类型/优先级                   | - agent/admin 可改 |
| - 描述                          | - 时间信息         |
| - 附加内容                      | - 返回列表         |
| - 跳转关联会话                  |                    |
+---------------------------------+--------------------+
```

### 3.7 数据看板

```text
+------------------------------------------------------+
| 指标卡 4 宫格                                        |
|                                                      |
| 工单状态分布              | 意图分布                |
| 图表/占位                 | 图表/占位               |
|                                                      |
| 平均置信度摘要                                     |
+------------------------------------------------------+
```

### 3.8 文档管理

```text
+------------------------------------------------------+
| 上传表单                                             |
| - 文件                                               |
| - 标题                                               |
| - 来源                                               |
| - 上传按钮                                           |
|                                                      |
| 状态筛选                                             |
|                                                      |
| 文档表格                                             |
| - 标题 / 状态 / 分块 / 时间 / 操作                   |
+------------------------------------------------------+
```

### 3.9 意图配置

```text
+-----------------------------------+------------------+
| 意图列表                          | 编辑面板         |
| - 名称                            | - display_name   |
| - route_target                    | - description    |
| - threshold                       | - keywords       |
| - priority                        | - examples       |
|                                   | - is_active      |
+-----------------------------------+------------------+
```

## 4. 页面骨架范围

本轮骨架实现覆盖：

- 路由切换
- 登录/注册表单
- 角色感知导航
- 聊天工作台框架
- 工单列表与详情骨架
- 管理看板骨架
- 文档管理骨架
- 意图配置骨架

本轮不追求完全实现：

- 完整视觉稿级细节
- 所有异常分支
- 表格复杂筛选
- 真正的图表库集成
- 文档预览
- 完整权限矩阵

## 5. 建议组件树

```text
App
- Router
  - AuthPage
    - LoginForm
    - RegisterForm
  - AppLayout
    - Sidebar
    - Topbar
    - NoticeBar
    - ChatPage
      - ConversationSidebar
      - MessageList
      - Composer
      - TicketPanel
    - TicketsPage
    - TicketDetailPage
    - DashboardPage
    - DocumentsPage
    - IntentsPage
```

## 6. 状态管理建议

当前静态骨架建议保持轻量：

- `localStorage`
  - `askflow.token`
  - `askflow.username`
- 内存状态
  - `currentRoute`
  - `currentUser`
  - `conversations`
  - `currentConversationId`
  - `messages`
  - `tickets`
  - `documents`
  - `intents`
  - `analytics`

后续如果切到 React/Vue，可平移为：

- 路由状态：React Router / Vue Router
- 服务端状态：TanStack Query / Vue Query
- 会话状态：Zustand / Pinia

## 7. 本轮实现目标

前端骨架要达到的效果：

1. 能登录并进入正确页面
2. 能在不同页面之间导航
3. 聊天页能承载现有 WebSocket 聊天能力
4. 管理页能读取已有管理接口
5. 结构上为后续组件化和框架迁移留出空间
