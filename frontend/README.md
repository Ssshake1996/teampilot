# TeamPilot Frontend

前端基于 Vue 3 + TypeScript + Vite。

## 实际版本要求

- Node.js `20.19+`

说明：

- `package.json` 中声明的 Node 范围是 `^20.19.0 || >=22.12.0`
- 当前 Docker 构建镜像使用的是 `node:20-alpine`

## 常用命令

### 安装依赖

```bash
npm install
```

### 启动开发环境

```bash
npm run dev
```

默认地址：

```text
http://localhost:5173
```

开发模式下会把 `/api` 代理到 `http://localhost:8000`。

### 生产构建

```bash
npm run build
```

## 推荐开发环境

- VS Code
- Vue (Official) / Volar 扩展

## 关键依赖

- Vue 3
- Vite 8
- TypeScript 6
- Element Plus 2.13
- Pinia 3
