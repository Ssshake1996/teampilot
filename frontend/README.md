# TeamPilot Frontend

## 运行要求

- Ubuntu `20.04.5+` 或 Windows `11+`
- Node.js `20.19+` 或 `22.12+`

说明：

- 当前 `package.json` 中声明的 Node 范围是 `^20.19.0 || >=22.12.0`
- Docker 构建镜像使用 `node:20-alpine`

## 安装依赖

```bash
npm install
```

## 启动开发环境

```bash
npm run dev
```

默认地址：

```text
http://localhost:5173
```

开发模式下 `/api` 会代理到 `http://localhost:8000`。

## 生产构建

```bash
npm run build
```

## 推荐开发工具

- VS Code
- Vue (Official) / Volar
