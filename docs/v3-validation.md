# V3 迁移验证记录

验证日期：2026-11-14（香港时间）。工作分支：`codex/v3-migration`。

## 验证对象

- 上游 V3 源码：`ec12c15ecd48c8ed2d58edaa7dc3deaabdf44c4f`，声明版本 `v3.2.6`。
- 官方标准版运行环境：`ghcr.io/jxxghp/moviepilot@sha256:0bb4c50a0b9c8597e9ffc910da52792f6fc64650f6caf66ed2e2a63ed9cec373`。
- 下载的标准 Python amd64 站点扩展原始 SHA256：`b71d49a65ceed565ff4c9c1519e1140f7be8607d826cdea0acd207302ae9ba9d`。
- 运行时报告认证资源版本 `3.0.6`、站点资源版本 `3.0.32`。

## 已通过

1. `python -m unittest discover -s tests -v`：3 项测试通过，覆盖 V2/V3 符号、位移修改范围、重复应用、不支持架构和未知符号拒绝修改、原子写入与权限保留。
2. `bash -n scripts/apply_patch.sh`、`git diff --check`、新增工作流 YAML 解析通过。
3. 在真实 V3 源码上重复执行叠加脚本，包初始化文件和 Dockerfile 均没有重复插入；临时 V2 目录的叠加和重复执行检查通过。
4. 对真实 V3 扩展的内存副本匹配到 1 处目标加载，重复执行字节保持不变。
5. 使用官方未修改镜像执行验证脚本，观测到 `auth_level=1`，脚本按预期拒绝通过，构成未应用补丁的对照。
6. 把迁移后的完整源码叠加到固定摘要的官方运行环境，成功构建 `moviepilot-v3-overlay:verify`，镜像 ID 为 `sha256:b3ba0a77aa26b930ecdbba941d6aa59162df5fd29b3a225df35125eecf7b7c62`。
7. 新镜像在 `--network none`、临时 SQLite、真实事务执行器和真实 IndexerModule 静态协议实现下通过验证：

   ```text
   PASS: app.application.site.sites, auth_level=2, catalog_entries=200, repeated installation unchanged
   ```

验证脚本不模拟认证等级，不访问 PT 站点。临时库没有配置活动站点，所以检查内置目录
`get_indexsites()`；`get_indexers()` 在这种环境下为空是正常行为。此结果不代表已经验证实际站点搜索或下载。

验证镜像使用的临时 Dockerfile 为：

```dockerfile
FROM ghcr.io/jxxghp/moviepilot@sha256:0bb4c50a0b9c8597e9ffc910da52792f6fc64650f6caf66ed2e2a63ed9cec373
COPY . /app
```

以叠加后的 `upstream` 为构建上下文。上游 `.dockerignore` 排除了本地 `.so` 和 `.bin`，
因此验证镜像保留官方原始二进制资源，由新的包导入钩子在容器运行时应用补丁。

## 尚未验证

- 完整上游 Dockerfile 从零重建：已尝试，但镜像层下载缓慢后中止；上述验证复用了官方运行环境，未重新安装所有系统和 Python 依赖。
- 完整应用的启动、HTTP readiness、实际 PT 站点搜索/下载和用户 V2 数据库迁移。
- ARM64、Windows、自由线程 V3t。
- 新工作流在 GitHub Actions 上的实际构建与推送；本次没有提交、推送或发布远程镜像。

新增 V3 工作流在完整源码构建后执行同一离线验证，成功后才向独立的
`DOCKER_USERNAME/moviepilot-v3` 仓库推送。V2 工作流保持独立。
