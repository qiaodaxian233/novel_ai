# Vendor 第三方资源

本目录存放离线引用的第三方前端资源,用于 QWebEngineView 内嵌网页。

| 文件 | 用途 | 版本 | License | 来源 |
|---|---|---|---|---|
| `vis-network.min.js` | 关系网络图(🕸️ 关系网 sub_tab) | 9.1.13 | Apache-2.0 / MIT 双授权 | https://github.com/visjs/vis-network |

## 为什么要 vendor 而不是 CDN

1. **离线写作场景**:用户可能断网写小说,CDN 加载失败会让 🕸️ 关系网 Tab 整个白屏
2. **加载稳定**:不依赖第三方 CDN 的可用性
3. **网络无关的体积**:619 KB,git 仓库可接受
