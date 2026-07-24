# 贡献指南 · Contributing

欢迎向拾光 · Lumen 贡献代码、文档、设计或任何改进。

## 知识产权说明

本项目采用 **AGPLv3 + 商业双许可** 模式。
商业授权收入支撑项目持续迭代，保证开源版本持续免费对外提供。

为保障能够持续提供两种授权模式，所有功能性代码贡献需要签署
[《ICLA 个人贡献许可协议》](ICLA.md)。
协议仅授予项目维护方分发权限，**您依然保留贡献代码自身著作权**，不会转让版权。

仅文档修正、拼写优化等微小改良同样欢迎提交。
如果您无法接受 ICLA 条款，可以自行维护项目 Fork，遵循 AGPLv3 协议使用代码。

## 提交流程

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feat/your-feature`
3. 提交代码（请写清楚 commit message）
4. 推送分支并发起 Pull Request
5. 在 PR 描述中确认已阅读并同意 [ICLA](ICLA.md)

## 代码风格

- 前端：Vue 3 Composition API + TypeScript，遵循项目已有的组件结构和命名惯例
- 后端：FastAPI + async/await，Pydantic 模型分层（schemas / models / services）
- 提交信息：中文或英文均可，简洁描述改动原因而非仅描述改了什么